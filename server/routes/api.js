const express = require('express');
const Patient = require('../models/Patient');
const Station = require('../models/Station');
const ScreeningSession = require('../models/ScreeningSession');
const Report = require('../models/Report');
const VitalTimeline = require('../models/VitalTimeline');
const ScreeningLog = require('../models/ScreeningLog');
const User = require('../models/User');
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

// GET /api/patients/:id/timeline
router.get('/patients/:id/timeline', async (req, res) => {
  const [timeline, logs] = await Promise.all([
    VitalTimeline.findOne({ patientId: req.params.id }),
    ScreeningLog.find({ patientId: req.params.id }).sort({ occurredAt: -1 }),
  ]);
  if (!timeline) return res.status(404).json({ error: 'Timeline not found' });
  res.json({ timeline, logs });
});

module.exports = router;
