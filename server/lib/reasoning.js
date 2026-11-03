const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

/*
 * The reasoning model: reasoning_model's triage expert system, served by python -m triage.demo_service. This server
 * starts it as a child process (building its demo cases first if they are missing) and restarts it if it dies,
 * unless REASONING_URL points at one already running. Live scans and the printed demo QR codes both run on it.
 */
const ROOT = path.join(__dirname, '..', '..', 'reasoning_model');
const SRC_DIR = path.join(ROOT, 'src');
const SAMPLE_DIR = path.join(ROOT, 'demo_samples');
const PORT = 5055;
const URL = process.env.REASONING_URL || `http://127.0.0.1:${PORT}`;

function pythonPath() {
  if (process.env.MODEL_PYTHON) return process.env.MODEL_PYTHON;
  // macOS/Linux venvs keep python in bin/, Windows ones in Scripts\
  for (const python of [path.join(ROOT, '.venv', 'bin', 'python'), path.join(ROOT, '.venv', 'Scripts', 'python.exe')]) {
    if (fs.existsSync(python)) return python;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function start() {
  if (process.env.REASONING_URL) return;
  if (!fs.existsSync(SAMPLE_DIR) || !fs.readdirSync(SAMPLE_DIR).some((f) => f.endsWith('.json'))) {
    spawnSync(pythonPath(), ['-m', 'triage.demo_samples', '--build'], { cwd: SRC_DIR, stdio: 'inherit' });
  }
  const child = spawn(pythonPath(), ['-m', 'triage.demo_service', '--port', String(PORT)], {
    cwd: SRC_DIR,
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  child.on('exit', (code) => {
    console.warn(`Reasoning service exited (${code}); restarting in 3 s`);
    setTimeout(start, 3000);
  });
  process.once('exit', () => child.kill());
}

// stop the service with the server: Ctrl+C or Render's SIGTERM would otherwise leave it holding its port
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => process.exit(0));

/** One request to the reasoning service; errors carry an HTTP status for the API to pass on. */
async function call(route, body) {
  let response;
  try {
    response = await fetch(`${URL}${route}`, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(60000),
    });
  } catch {
    throw Object.assign(new Error('The reasoning model is not running. Try again in a moment.'), { status: 503 });
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Object.assign(new Error(data.error || 'The reasoning model could not run this case.'), {
      status: response.status,
    });
  }
  return data;
}

/** Runs the triage on one demo case; resolves to the result screen's data and how long it took. */
async function run(sampleId, useLlm = true) {
  const started = Date.now();
  const result = await call('/run', { sample_id: sampleId, use_llm: useLlm });
  return { result, modelMs: Date.now() - started };
}

let next = 0;

/** The next demo case, round-robin, so consecutive live scans show different results. */
async function nextSample() {
  const samples = await call('/samples');
  if (!samples.length) throw new Error('The reasoning model has no demo cases.');
  const sample = samples[next % samples.length];
  next += 1;
  return sample;
}

async function health() {
  try {
    const response = await fetch(`${URL}/health`, { signal: AbortSignal.timeout(3000) });
    return response.ok ? await response.json() : { ok: false };
  } catch {
    return { ok: false };
  }
}

module.exports = { start, call, run, nextSample, health, pythonPath };
