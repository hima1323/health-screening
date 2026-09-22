const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const express = require('express');
const multer = require('multer');
const User = require('../models/User');
const Patient = require('../models/Patient');
const requireUser = require('../middleware/requireUser');
const { issueToken } = require('../lib/token');
const google = require('../lib/google');

const router = express.Router();

const MIN_PASSWORD = 8;
const UPLOAD_DIR = path.join(__dirname, '..', 'uploads');
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const ALLOWED_TYPES = /^(application\/pdf|image\/(png|jpe?g|heic|webp)|text\/plain)$/;

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const upload = multer({
  storage: multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOAD_DIR),
    filename: (req, file, cb) =>
      cb(null, `${crypto.randomBytes(10).toString('hex')}${path.extname(file.originalname)}`),
  }),
  limits: { fileSize: MAX_UPLOAD_BYTES, files: 10 },
  fileFilter: (req, file, cb) =>
    ALLOWED_TYPES.test(file.mimetype)
      ? cb(null, true)
      : cb(new Error('Only PDF, image or text reports can be uploaded')),
});

/** Turns a mongoose validation or duplicate-key failure into one readable message. */
function describe(err) {
  if (err.code === 11000) return 'An account with that email already exists';
  if (err.name === 'ValidationError') return Object.values(err.errors)[0].message;
  return err.message;
}

const session = (user) => ({ token: issueToken(user), user: user.toClient() });

// GET /api/auth/providers — what the sign-in screen may offer
router.get('/providers', (req, res) =>
  res.json({ google: google.isConfigured(), googleClientId: google.clientId || null })
);

// POST /api/auth/google — trade a Google ID token for one of ours
router.post('/google', async (req, res) => {
  if (!google.isConfigured()) return res.status(503).json({ error: 'Google sign-in is not configured' });

  try {
    const identity = await google.verifyCredential(req.body?.credential);

    // an existing password account with the same address is linked rather than duplicated
    const user =
      (await User.findOne({ $or: [{ googleId: identity.googleId }, { email: identity.email }] })) ||
      new User({ name: identity.name, email: identity.email });

    user.googleId = identity.googleId;
    user.avatarUrl = identity.avatarUrl;
    user.lastSignInAt = new Date();
    await user.save();

    res.json(session(user));
  } catch (err) {
    const ours = err.code === 11000 || err.name === 'ValidationError';
    res.status(401).json({ error: ours ? describe(err) : 'That Google sign-in could not be verified' });
  }
});

// POST /api/auth/register — create an account
router.post('/register', async (req, res) => {
  const { name, email, password } = req.body || {};

  if (!name || !String(name).trim()) return res.status(400).json({ error: 'Name is required' });
  if (!password || String(password).length < MIN_PASSWORD) {
    return res.status(400).json({ error: `Password must be at least ${MIN_PASSWORD} characters` });
  }

  try {
    const user = new User({ name: String(name).trim(), email, lastSignInAt: new Date() });
    await user.setPassword(String(password));
    await user.save();
    res.status(201).json(session(user));
  } catch (err) {
    res.status(err.code === 11000 ? 409 : 400).json({ error: describe(err) });
  }
});

// POST /api/auth/login — open a session for an existing account
router.post('/login', async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: 'Email and password are required' });

  // the hash is select:false, so ask for it explicitly
  const user = await User.findOne({ email: String(email).toLowerCase().trim() }).select('+passwordHash +googleId');
  // the same message either way, so the response never confirms which emails exist
  if (!user || !(await user.verifyPassword(String(password)))) {
    return res.status(401).json({ error: 'That email and password do not match' });
  }

  user.lastSignInAt = new Date();
  await user.save();
  res.json(session(user));
});

// GET /api/auth/me — restore the session the browser remembered
router.get('/me', requireUser, (req, res) => res.json({ user: req.user.toClient() }));

// PUT /api/auth/me/profile — the onboarding questionnaire
router.put('/me/profile', requireUser, async (req, res) => {
  const { fullName, age, sex, phone, heightCm, weightKg, bloodGroup, conditions, medications, consentAccepted } =
    req.body || {};

  const user = req.user;
  user.profile = {
    fullName,
    age,
    sex: sex || '',
    phone: phone || '',
    heightCm: heightCm === '' || heightCm === undefined ? undefined : Number(heightCm),
    weightKg: weightKg === '' || weightKg === undefined ? undefined : Number(weightKg),
    bloodGroup: bloodGroup || '',
    conditions: conditions || '',
    medications: medications || '',
    consentAccepted: Boolean(consentAccepted),
  };
  user.profileCompletedAt = new Date();

  try {
    // The screening history hangs off a Patient record, so link the user to one
    // and carry the details they just gave us onto it.
    const patient = user.patientId ? await Patient.findById(user.patientId) : await Patient.findOne();
    if (patient) {
      patient.name = user.profile.fullName;
      patient.age = user.profile.age;
      await patient.save();
      user.patientId = patient._id;
    }

    await user.save();
    res.json({ user: user.toClient() });
  } catch (err) {
    res.status(400).json({ error: describe(err) });
  }
});

// POST /api/auth/me/reports — attach reports from an earlier clinic visit
router.post('/me/reports', requireUser, upload.array('reports', 10), async (req, res) => {
  const files = req.files || [];
  if (!files.length) return res.status(400).json({ error: 'No files were received' });

  const user = req.user;
  files.forEach((file) => {
    user.pastReports.push({
      label: file.originalname.replace(/\.[^.]+$/, ''),
      originalName: file.originalname,
      storedName: file.filename,
      mimeType: file.mimetype,
      sizeBytes: file.size,
    });
  });
  await user.save();

  res.status(201).json({ user: user.toClient() });
});

// DELETE /api/auth/me/reports/:reportId — remove an upload and its bytes
router.delete('/me/reports/:reportId', requireUser, async (req, res) => {
  const user = req.user;
  const report = user.pastReports.id(req.params.reportId);
  if (!report) return res.status(404).json({ error: 'Report not found' });

  fs.rm(path.join(UPLOAD_DIR, report.storedName), { force: true }, () => {});
  report.deleteOne();
  await user.save();

  res.json({ user: user.toClient() });
});

// multer rejects oversized or wrong-typed files with an error rather than a status
router.use((err, req, res, next) => {
  if (!err) return next();
  res.status(400).json({ error: err.code === 'LIMIT_FILE_SIZE' ? 'Each report must be under 15 MB' : err.message });
});

module.exports = router;
