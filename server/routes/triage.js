const express = require('express');
const reasoning = require('../lib/reasoning');

/*
 * The reasoning model's demo cases. A printed demo QR (server/scripts/demo-qr.js) names one case; the patient scans
 * it from the Scan Hub and the client asks here for the rule-based triage on it (lib/reasoning.js). Draft rules,
 * sample data only.
 */
const router = express.Router();

const handle = (fn) => async (req, res) => {
  try {
    res.json(await fn(req));
  } catch (err) {
    res.status(err.status || 500).json({ error: err.message });
  }
};

// GET /api/triage/samples — the demo sample files a printed QR can name
router.get('/samples', handle(() => reasoning.call('/samples')));

// POST /api/triage/run { sample, explain } → the result screen's data
router.post(
  '/run',
  handle((req) => reasoning.call('/run', { sample_id: req.body?.sample, use_llm: req.body?.explain !== false }))
);

// POST /api/triage/runs/:runId/ask { question } → a follow-up answer
router.post(
  '/runs/:runId/ask',
  handle((req) => reasoning.call('/ask', { run_id: req.params.runId, question: req.body?.question }))
);

module.exports = router;
