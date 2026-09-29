const path = require('path');
const express = require('express');
const Patient = require('../models/Patient');
const Station = require('../models/Station');
const ScreeningSession = require('../models/ScreeningSession');
const Report = require('../models/Report');
const ScreeningLog = require('../models/ScreeningLog');
const User = require('../models/User');
const StudySession = require('../models/StudySession');
const { bearerFrom, readToken } = require('../lib/token');

const router = express.Router();

// GET /api/primary — resolves the demo patient/session ids so the client never hardcodes them
router.get('/primary', async (req, res) => {
  // A signed-in user points at their own patient record; otherwise fall back to the seeded demo one.
  const userId = readToken(bearerFrom(req) || '');
  const user = userId ? await User.findById(userId) : null;

  const linked = user && user.patientId ? await Patient.findById(user.patientId) : null;
  const patient = linked || (await Patient.findOne());
  if (!patient) return res.status(404).json({ error: 'No patient found. Run the seed script.' });
  const session = await ScreeningSession.findOne({ patientId: patient._id });
  res.json({ patientId: patient._id, sessionId: session ? session.sessionId : null });
});

// GET /api/patients/:id/scan-hub — data for the Scan Hub page
router.get('/patients/:id/scan-hub', async (req, res) => {
  const patient = await Patient.findById(req.params.id);
  if (!patient) return res.status(404).json({ error: 'Patient not found' });

  const [station, latestClearedLog] = await Promise.all([
    Station.findOne({ stationId: 'station-2' }),
    ScreeningLog.findOne({ patientId: patient._id, status: 'Cleared' }).sort({ occurredAt: -1 }),
  ]);

  res.json({
    patient: { name: patient.name, age: patient.age },
    aura: patient.aura,
    consent: patient.consent,
    station,
    lastScreeningReport: latestClearedLog
      ? {
          dateLabel: latestClearedLog.dateLabel,
          summary: 'all readings in normal harmony',
          status: latestClearedLog.status,
          pulse: latestClearedLog.heartRate,
          temp: latestClearedLog.temp,
          breath: 16,
        }
      : null,
  });
});

// GET /api/sessions/:sessionId/active-scan
router.get('/sessions/:sessionId/active-scan', async (req, res) => {
  const session = await ScreeningSession.findOne({ sessionId: req.params.sessionId }).populate(
    'patientId',
    'name age'
  );
  if (!session) return res.status(404).json({ error: 'Session not found' });
  res.json(session);
});

// GET /api/sessions/:sessionId/report
router.get('/sessions/:sessionId/report', async (req, res) => {
  const report = await Report.findOne({ sessionId: req.params.sessionId }).populate(
    'patientId',
    'name age'
  );
  if (!report) return res.status(404).json({ error: 'Report not found' });
  res.json(report);
});

// GET /api/study-sessions — the past sessions list, with an overview sketch of each track
router.get('/study-sessions', async (req, res) => {
  const sessions = await StudySession.find()
    .select('-metrics -pipeline -metricDefs')
    .sort({ 'source.dataset': 1, sessionKey: 1 })
    .lean();

  // a min/max envelope per bucket, the way an audio overview is drawn: averaging would
  // cancel an oscillating pulse out, the envelope keeps its shape at any width
  const BUCKETS = 64;
  const envelope = (values) => {
    const n = Math.min(BUCKETS, values.length);
    const lo = [];
    const hi = [];
    for (let i = 0; i < n; i += 1) {
      const chunk = values.slice(Math.floor((i * values.length) / n), Math.floor(((i + 1) * values.length) / n));
      lo.push(Math.min(...chunk));
      hi.push(Math.max(...chunk));
    }
    return { lo, hi };
  };

  res.json({
    sessions: sessions.map(({ tracks, ...session }) => ({
      ...session,
      preview: tracks.map(({ key, label, group, values }) => ({ key, label, group, ...envelope(values) })),
    })),
  });
});

// GET /api/study-sessions/:key — one session with its signals and analysis
router.get('/study-sessions/:key', async (req, res) => {
  const session = await StudySession.findOne({ sessionKey: req.params.key });
  if (!session) return res.status(404).json({ error: 'Session not found' });
  res.json({ session });
});

// GET /api/study-sessions/:key/frames — the raw thermogram, fetched once by the viewer
router.get('/study-sessions/:key/frames', async (req, res) => {
  const session = await StudySession.findOne({ sessionKey: req.params.key }).select('frames').lean();
  if (!session?.frames) return res.status(404).json({ error: 'This session has no thermal frames' });
  // basename keeps the lookup inside the sessions folder whatever the stored name says
  const file = path.join(__dirname, '..', 'data', 'sessions', path.basename(session.frames.file));
  res.set('Cache-Control', 'public, max-age=86400');
  res.type('application/octet-stream').sendFile(file);
});

module.exports = router;
