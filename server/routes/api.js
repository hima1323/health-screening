const path = require('path');
const express = require('express');
const Patient = require('../models/Patient');
const Station = require('../models/Station');
const Report = require('../models/Report');
const ScreeningLog = require('../models/ScreeningLog');
const User = require('../models/User');
const StudySession = require('../models/StudySession');
const QRCode = require('qrcode');
const { bearerFrom, readToken } = require('../lib/token');
const { issueStationCode, readStationCode } = require('../lib/stationCode');
const { patientFor } = require('../lib/patient');

const router = express.Router();

// GET /api/primary — resolves the demo patient/session ids so the client never hardcodes them
router.get('/primary', async (req, res) => {
  // A signed-in user gets their own patient record; a visitor falls back to the seeded demo one.
  const userId = readToken(bearerFrom(req) || '');
  const user = userId ? await User.findById(userId) : null;

  const patient = (user && (await patientFor(user))) || (await Patient.findOne({ ownerId: null }));
  if (!patient) return res.status(404).json({ error: 'No patient found. Run the seed script.' });
  // the newest report is the one the Report tab shows
  const latest = await Report.findOne({ patientId: patient._id }).sort({ recordedAt: -1 }).select('sessionId').lean();
  res.json({ patientId: patient._id, sessionId: latest ? latest.sessionId : null });
});

// GET /api/patients/:id/scan-hub — data for the Scan Hub page
router.get('/patients/:id/scan-hub', async (req, res) => {
  const patient = await Patient.findById(req.params.id);
  if (!patient) return res.status(404).json({ error: 'Patient not found' });

  const [station, latestLog, latestReport] = await Promise.all([
    Station.findOne({ stationId: 'station-2' }),
    ScreeningLog.findOne({ patientId: patient._id }).sort({ occurredAt: -1 }),
    Report.findOne({ patientId: patient._id }).sort({ recordedAt: -1 }).select('respiration').lean(),
  ]);

  res.json({
    patient: { name: patient.name, age: patient.age },
    aura: patient.aura,
    consent: patient.consent,
    station,
    lastScreeningReport: latestLog
      ? {
          dateLabel: latestLog.dateLabel,
          summary: latestLog.status === 'Cleared' ? 'all readings in normal harmony' : 'one or more readings to review',
          status: latestLog.status,
          pulse: latestLog.heartRate,
          temp: latestLog.temp ?? null,
          breath: latestReport?.respiration?.value ?? null,
        }
      : null,
  });
});

// GET /api/sessions/:sessionId/report
router.get('/sessions/:sessionId/report', async (req, res) => {
  const report = await Report.findOne({ sessionId: req.params.sessionId }).populate(
    'patientId',
    'name age ownerId'
  );
  // a report from an account's own scan opens only for that account; the seeded demo ones open for anyone
  const owner = report?.patientId?.ownerId;
  if (!report || (owner && String(owner) !== readToken(bearerFrom(req) || ''))) {
    return res.status(404).json({ error: 'Report not found' });
  }
  res.json(report);
});

// GET /api/stations/:stationId/code — the signed QR the kiosk displays; it refetches before expiresAt
router.get('/stations/:stationId/code', async (req, res) => {
  const station = await Station.findOne({ stationId: req.params.stationId }).select('stationId').lean();
  if (!station) return res.status(404).json({ error: 'Station not found' });
  const { code, expiresAt } = issueStationCode(station.stationId);
  const svg = await QRCode.toString(code, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' });
  res.set('Cache-Control', 'no-store');
  res.json({ stationId: station.stationId, code, expiresAt, svg });
});

// POST /api/stations/verify — is a scanned QR one of our kiosk codes? { code } → { stationId }
router.post('/stations/verify', async (req, res) => {
  const { stationId, sample, error } = readStationCode(req.body?.code);
  if (error) return res.status(400).json({ error });
  const station = await Station.exists({ stationId });
  if (!station) return res.status(400).json({ error: 'This station is no longer in service.' });
  res.json({ stationId, sample: sample || null });
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
