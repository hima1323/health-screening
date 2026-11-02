const express = require('express');
const QRCode = require('qrcode');
const { issueStationCode, readStationCode } = require('../lib/stationCode');

/*
 * Demo of the reasoning model inside Aura Screen. The kiosk picks a demo sample file (cases from MIMIC-IV-ED, Yale ED
 * and our rPPG test videos, built by reasoning_model: python -m triage.demo_samples --build) and shows a signed,
 * short-lived QR code that carries its id. The phone scans it, and the server asks the local reasoning service
 * (python -m triage.demo_service) to run the rule-based triage on that file. No database is needed, so the demo also
 * runs with DEMO_WITHOUT_DB=1. Draft rules, sample data only.
 */
const REASONING_URL = process.env.REASONING_URL || 'http://127.0.0.1:5055';
const router = express.Router();

async function reasoning(path, body) {
  let response;
  try {
    response = await fetch(`${REASONING_URL}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(60000),
    });
  } catch {
    const err = new Error('The reasoning service is not running. Start it with start_aura_demo.bat.');
    err.status = 503;
    throw err;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(data.error || 'The reasoning service could not run this sample.');
    err.status = response.status;
    throw err;
  }
  return data;
}

const handle = (fn) => async (req, res) => {
  try {
    res.json(await fn(req));
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
};

// GET /api/triage/samples — the demo sample files the kiosk can put into a QR code
router.get('/samples', handle(() => reasoning('/samples')));

// GET /api/triage/code?station=station-2&sample=<id> — a signed QR that carries the demo sample (no database)
router.get(
  '/code',
  handle(async (req) => {
    const stationId = String(req.query.station || 'station-2');
    const sample = req.query.sample ? String(req.query.sample) : undefined;
    const { code, expiresAt } = issueStationCode(stationId, sample);
    const svg = await QRCode.toString(code, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' });
    return { stationId, sample: sample || null, code, expiresAt, svg };
  })
);

// POST /api/triage/verify { code } → { stationId, sample } — like /stations/verify, without the database
router.post(
  '/verify',
  handle(async (req) => {
    const { stationId, sample, error } = readStationCode(req.body?.code);
    if (error) throw Object.assign(new Error(error), { status: 400 });
    if (!sample) {
      throw Object.assign(new Error('This kiosk code carries no demo sample. Pick one on the kiosk screen.'), {
        status: 400,
      });
    }
    return { stationId, sample };
  })
);

// POST /api/triage/run { sample, explain } → the result screen's data
router.post(
  '/run',
  handle((req) => reasoning('/run', { sample_id: req.body?.sample, use_llm: req.body?.explain !== false }))
);

// POST /api/triage/runs/:runId/ask { question } → a follow-up answer
router.post(
  '/runs/:runId/ask',
  handle((req) => reasoning('/ask', { run_id: req.params.runId, question: req.body?.question }))
);

module.exports = router;
