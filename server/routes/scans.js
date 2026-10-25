const crypto = require('crypto');
const express = require('express');
const mongoose = require('mongoose');
const Scan = require('../models/Scan');
const Station = require('../models/Station');
const Report = require('../models/Report');
const ScreeningLog = require('../models/ScreeningLog');
const requireUser = require('../middleware/requireUser');
const { readStationCode } = require('../lib/stationCode');
const { patientFor } = require('../lib/patient');
const model = require('../lib/model');
const { rangeStatus } = require('../lib/ranges');

const router = express.Router();

// how long the station "records"; the demo station replays a recorded sample in this time
const CAPTURE_SECONDS = Number(process.env.DEMO_CAPTURE_SECONDS) || 12;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// POST /api/scans — the phone scanned a kiosk code: start a scan at that station. { code } → scan
// Without a code (the scanner's "Continue without camera") staff link the session at the desk, which here is
// the demo station.
// ponytail: any signed-in patient can start a code-less scan; gate it on a staff action before real stations
router.post('/', requireUser, async (req, res) => {
  const { stationId, error } = req.body?.code ? readStationCode(req.body.code) : { stationId: 'station-2' };
  if (error) return res.status(400).json({ error });
  if (!(await Station.exists({ stationId }))) return res.status(400).json({ error: 'This station is no longer in service.' });

  const patient = await patientFor(req.user);
  if (!patient) return res.status(400).json({ error: 'Finish your details before your first scan.' });

  // two requests at once from one account start one scan: the second waits for the first, then resumes it
  const key = String(req.user._id);
  while (starting.has(key)) await starting.get(key);
  let release;
  starting.set(key, new Promise((resolve) => (release = resolve)));
  try {
    const [status, body] = await startOrResume(req.user, patient, stationId);
    res.status(status).json(body);
  } finally {
    starting.delete(key);
    release();
  }
});

// ponytail: in-memory per-account lock, fine for one server instance; use a unique DB index if it scales out
const starting = new Map();

async function startOrResume(user, patient, stationId) {
  // a double tap or a second scan of the code resumes the scan already running
  const running = await Scan.findOne({
    userId: user._id,
    stage: { $nin: ['done', 'failed'] },
    createdAt: { $gt: new Date(Date.now() - 5 * 60 * 1000) },
  });
  if (running) return [200, { scan: running.toClient() }];

  const sample = model.nextSample();
  const scan = await Scan.create({
    userId: user._id,
    patientId: patient._id,
    stationId,
    captureSeconds: CAPTURE_SECONDS,
    stages: { linked: new Date() },
    sample: { key: sample.key, task: sample.task, dataset: sample.dataset, windows: sample.windows.length, sensors: sample.sensors },
  });
  run(scan, sample, patient).catch((err) => console.error('Scan pipeline crashed', err));
  return [201, { scan: scan.toClient() }];
}

// GET /api/scans/:id — where the patient's scan is; the phone polls this
router.get('/:id', requireUser, async (req, res) => {
  const scan = mongoose.isValidObjectId(req.params.id) && (await Scan.findOne({ _id: req.params.id, userId: req.user._id }));
  if (!scan) return res.status(404).json({ error: 'Scan not found' });
  res.json({ scan: scan.toClient() });
});

async function run(scan, sample, patient) {
  const step = async (stage, fields = {}) => {
    Object.assign(scan, fields, { stage });
    scan.stages.set(stage, new Date());
    await scan.save();
  };

  try {
    await step('capturing');
    await sleep(CAPTURE_SECONDS * 1000);

    await step('uploading');
    const { result, bytes, modelMs } = await model.predict(sample);
    await step('analysing', { upload: { bytes, modelMs } });

    const report = await writeReport({ scan, sample, patient, result, bytes, modelMs });
    await step('done', { sessionId: report.sessionId });
  } catch (err) {
    const reason = err.name === 'TimeoutError' || err.cause?.code === 'ECONNREFUSED'
      ? 'The model server did not answer. Try the scan again in a moment.'
      : err.message;
    await step('failed', { error: reason });
  }
}

async function writeReport({ scan, sample, patient, result, bytes, modelMs }) {
  const { summary, windows, vitals } = result;
  const heart = vitals.heartRate && Math.round(vitals.heartRate);
  const breath = vitals.breathingRate && Math.round(vitals.breathingRate);
  const now = new Date();

  const report = await Report.create({
    sessionId: await freeSessionId(),
    patientId: patient._id,
    recordedAt: now,
    heartRate: heart && reading(heart, '60–100 bpm', 'From the ECG during the capture.'),
    respiration: breath && reading(breath, '12–20 /min', 'From the breathing belt during the capture.'),
    shareCode: shareCode(),
    encryptionNote: 'Kept on the clinic server. Only a doctor you give the code to can open it.',
    model: {
      scanId: scan._id,
      stationId: scan.stationId,
      summary,
      windows: windows.map(({ label, probability_high, confidence, abstain, agents }) => ({
        label,
        probability_high,
        confidence,
        abstain,
        agents,
      })),
      skinTempC: vitals.skinTempC,
      sample: {
        key: sample.key,
        dataset: sample.dataset,
        subject: sample.subject,
        task: sample.task,
        truth: sample.truth,
        durationSeconds: sample.durationSeconds,
        windowSeconds: sample.windowSeconds,
      },
      trainedOnSubjects: result.trained_on_subjects,
      transfer: { bytes, modelMs },
    },
  });

  const outOfRange = [report.heartRate, report.respiration].some((r) => r && r.status !== 'Normal');
  await ScreeningLog.create({
    patientId: patient._id,
    type: 'Contactless scan',
    dateLabel: `${new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(now)} · Live scan`,
    location: `Central Diagnostic Centre · ${scan.stationId.replace(/^station-/, 'Station ')}`,
    heartRate: heart,
    status: outOfRange || (summary.label === 'high' && !summary.abstain) ? 'Watch' : 'Cleared',
    occurredAt: now,
  });
  return report;
}

function reading(value, normalRange, note) {
  return { value, normalRange, status: rangeStatus(value, normalRange), note };
}

async function freeSessionId() {
  for (;;) {
    const id = `S-${crypto.randomInt(1000, 10000)}`;
    if (!(await Report.exists({ sessionId: id }))) return id;
  }
}

/** "482-KTW": three digits and three letters, without the look-alikes I and O. */
function shareCode() {
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const pick = () => letters[crypto.randomInt(letters.length)];
  return `${crypto.randomInt(100, 1000)}-${pick()}${pick()}${pick()}`;
}

/** The kiosk's live view of its own station: the stage only, nothing about who is being scanned. */
async function stationLive(req, res) {
  const scan = await Scan.findOne({ stationId: req.params.stationId, updatedAt: { $gt: new Date(Date.now() - 90 * 1000) } })
    .sort({ createdAt: -1 })
    .lean();
  res.set('Cache-Control', 'no-store');
  if (!scan) return res.json({ scan: null });
  res.json({
    scan: {
      stage: scan.stage,
      stages: scan.stages,
      captureSeconds: scan.captureSeconds,
      task: scan.sample?.task,
      sensors: scan.sample?.sensors,
    },
  });
}

module.exports = { router, stationLive };
