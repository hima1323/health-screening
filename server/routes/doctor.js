const express = require('express');
const mongoose = require('mongoose');
const Doctor = require('../models/Doctor');
const Report = require('../models/Report');
const ReportShare = require('../models/ReportShare');
const ScreeningLog = require('../models/ScreeningLog');
const requireDoctor = require('../middleware/requireDoctor');
const { issueDoctorToken } = require('../lib/token');
const google = require('../lib/google');

const router = express.Router();

// POST /api/doctor/login — doctors sign in with the account the clinic created for them
// ponytail: no lockout after repeated failures; add one before real accounts
router.post('/login', async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: 'Email and password are required' });

  const doctor = await Doctor.findOne({ email: String(email).toLowerCase().trim() }).select('+passwordHash');
  // one message either way, so the response never confirms which emails exist
  if (!doctor || !(await doctor.verifyPassword(String(password)))) {
    return res.status(401).json({ error: 'That email and password do not match a doctor account' });
  }

  doctor.lastSignInAt = new Date();
  await doctor.save();
  res.json({ token: issueDoctorToken(doctor), doctor: doctor.toClient() });
});

// POST /api/doctor/google — sign in with Google. Only a Google account whose verified email the
// clinic has registered as a doctor gets in; anyone else is turned away, never signed up.
router.post('/google', async (req, res) => {
  if (!google.isConfigured()) return res.status(503).json({ error: 'Google sign-in is not configured' });

  let identity;
  try {
    identity = await google.verifyCredential(req.body?.credential);
  } catch {
    return res.status(401).json({ error: 'That Google sign-in could not be verified' });
  }

  const doctor = await Doctor.findOne({
    $or: [{ googleId: identity.googleId }, { email: identity.email.toLowerCase() }],
  });
  if (!doctor) {
    return res.status(403).json({
      error: `${identity.email} is not registered as a doctor here. Ask your clinic to add you.`,
    });
  }

  doctor.googleId = identity.googleId; // linked on first sign-in, so a later email change still finds them
  doctor.avatarUrl = identity.avatarUrl;
  doctor.lastSignInAt = new Date();
  await doctor.save();
  res.json({ token: issueDoctorToken(doctor), doctor: doctor.toClient() });
});

router.use(requireDoctor);

// GET /api/doctor/me — restore the session the browser remembered
router.get('/me', (req, res) => res.json({ doctor: req.doctor.toClient() }));

const REPORT_FIELDS = 'sessionId shareCode recordedAt nurseCheck heartRate bodyTemp respiration';

// GET /api/doctor/patients — everyone who has shared a report with this doctor, with those reports
router.get('/patients', async (req, res) => {
  const shares = await ReportShare.find({ doctorId: req.doctor._id })
    .populate('reportId', REPORT_FIELDS)
    .populate('patientId', 'name age')
    .sort({ sharedAt: -1 })
    .lean();

  const byPatient = new Map();
  for (const share of shares) {
    if (!share.reportId || !share.patientId) continue; // the report or patient was deleted since
    const key = share.patientId._id.toString();
    if (!byPatient.has(key)) byPatient.set(key, { patient: share.patientId, reports: [] });
    byPatient.get(key).reports.push({ ...share.reportId, sharedAt: share.sharedAt, lastOpenedAt: share.lastOpenedAt });
  }
  res.json({ patients: [...byPatient.values()] });
});

// GET /api/doctor/patients/:patientId — one patient: the reports they shared with this doctor and
// their screening history. A doctor can open only patients who shared at least one report with them.
router.get('/patients/:patientId', async (req, res) => {
  const { patientId } = req.params;
  if (!mongoose.isValidObjectId(patientId)) return res.status(404).json({ error: 'Patient not found' });

  const shares = await ReportShare.find({ doctorId: req.doctor._id, patientId })
    .populate('reportId', REPORT_FIELDS)
    .populate('patientId', 'name age')
    .lean();
  const visible = shares.filter((s) => s.reportId && s.patientId);
  // the same answer for "no such patient" and "not shared with you", so ids can't be probed
  if (visible.length === 0) return res.status(404).json({ error: 'Patient not found' });

  const history = await ScreeningLog.find({ patientId }).select('-patientId -__v').sort({ occurredAt: -1 }).lean();
  res.json({
    patient: visible[0].patientId,
    reports: visible.map((s) => ({ ...s.reportId, sharedAt: s.sharedAt, lastOpenedAt: s.lastOpenedAt })),
    history,
  });
});

// GET /api/doctor/reports/:shareCode — open a report with the patient's code. The first open
// adds it to this doctor's list; after that it opens from the list.
// ponytail: wrong codes aren't rate-limited; the sign-in narrows it to known doctors for now
router.get('/reports/:shareCode', async (req, res) => {
  const shareCode = String(req.params.shareCode).trim().toUpperCase();
  const report = await Report.findOne({ shareCode }).populate('patientId', 'name age').lean();
  if (!report) return res.status(404).json({ error: 'No report matches that code. Check it with the patient.' });

  const patient = report.patientId;
  const [share, history] = await Promise.all([
    ReportShare.findOneAndUpdate(
      { doctorId: req.doctor._id, reportId: report._id },
      { $set: { lastOpenedAt: new Date() }, $setOnInsert: { patientId: patient._id } },
      { upsert: true, new: true }
    ).lean(),
    ScreeningLog.find({ patientId: patient._id }).select('-patientId -__v').sort({ occurredAt: -1 }).lean(),
  ]);

  const { patientId, ...rest } = report;
  res.json({ report: { ...rest, sharedAt: share.sharedAt }, patient, history });
});

module.exports = router;
