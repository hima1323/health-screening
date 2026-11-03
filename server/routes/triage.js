const express = require('express');

/*
 * Demo of the reasoning model inside Aura Screen. A printed demo QR (server/scripts/demo-qr.js) names one demo sample
 * file (built by reasoning_model: python -m triage.demo_samples --build); the patient scans it from the Scan Hub, and
 * the server asks the local reasoning service (python -m triage.demo_service) to run the rule-based triage on that
 * file. Draft rules, sample data only.
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

// GET /api/triage/samples — the demo sample files a printed QR can name
router.get('/samples', handle(() => reasoning('/samples')));

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
