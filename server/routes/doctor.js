const express = require('express');
const mongoose = require('mongoose');
const Doctor = require('../models/Doctor');
const Report = require('../models/Report');
const ReportShare = require('../models/ReportShare');
const ScreeningLog = require('../models/ScreeningLog');
const StudySession = require('../models/StudySession');
const DoctorNote = require('../models/DoctorNote');
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

const REPORT_FIELDS = 'sessionId shareCode recordedAt nurseCheck heartRate bodyTemp respiration model.summary model.sample';

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

  const [history, sessions] = await Promise.all([
    ScreeningLog.find({ patientId }).select('-patientId -__v').sort({ occurredAt: -1 }).lean(),
    StudySession.find({ patientId }).select('sessionKey label recordedOn summary source.dataset').sort({ sessionKey: 1 }).lean(),
  ]);
  res.json({
    patient: visible[0].patientId,
    reports: visible.map((s) => ({ ...s.reportId, sharedAt: s.sharedAt, lastOpenedAt: s.lastOpenedAt })),
    history,
    sessions,
  });
});

// GET /api/doctor/patients/:patientId/sessions/:key — one recorded session of that patient: the model's
// output and all the original data. Same rule as the patient: only after they shared a report with this doctor.
router.get('/patients/:patientId/sessions/:key', async (req, res) => {
  const { patientId, key } = req.params;
  if (!mongoose.isValidObjectId(patientId)) return res.status(404).json({ error: 'Session not found' });
  const [shared, session] = await Promise.all([
    ReportShare.exists({ doctorId: req.doctor._id, patientId }),
    StudySession.findOne({ sessionKey: key, patientId }).populate('patientId', 'name age').lean(),
  ]);
  if (!shared || !session) return res.status(404).json({ error: 'Session not found' });
  const { patientId: patient, ...rest } = session;
  res.json({ session: rest, patient });
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

// GET /api/doctor/patients/:patientId/notes — this doctor's own notes on a patient who shared with them
router.get('/patients/:patientId/notes', async (req, res) => {
  const { patientId } = req.params;
  if (!(await sharedWith(req.doctor, patientId))) return res.status(404).json({ error: 'Patient not found' });
  const notes = await DoctorNote.find({ doctorId: req.doctor._id, patientId }).sort({ createdAt: -1 }).lean();
  res.json({ notes });
});

// POST /api/doctor/patients/:patientId/notes — { text }
router.post('/patients/:patientId/notes', async (req, res) => {
  const { patientId } = req.params;
  const text = String(req.body?.text ?? '').trim();
  if (!text) return res.status(400).json({ error: 'Write something first' });
  if (!(await sharedWith(req.doctor, patientId))) return res.status(404).json({ error: 'Patient not found' });
  try {
    const note = await DoctorNote.create({ doctorId: req.doctor._id, patientId, text });
    res.status(201).json({ note });
  } catch (err) {
    res.status(400).json({ error: err.errors?.text?.message || 'That note could not be saved' });
  }
});

// DELETE /api/doctor/notes/:noteId — only the doctor who wrote it
router.delete('/notes/:noteId', async (req, res) => {
  if (!mongoose.isValidObjectId(req.params.noteId)) return res.status(404).json({ error: 'Note not found' });
  const { deletedCount } = await DoctorNote.deleteOne({ _id: req.params.noteId, doctorId: req.doctor._id });
  if (!deletedCount) return res.status(404).json({ error: 'Note not found' });
  res.status(204).end();
});

function sharedWith(doctor, patientId) {
  return mongoose.isValidObjectId(patientId) && ReportShare.exists({ doctorId: doctor._id, patientId });
}

module.exports = router;
