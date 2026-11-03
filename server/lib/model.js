const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

/*
 * The reasoning model runs in model_service/serve.py (Python: LightGBM agents + fusion). This server starts it
 * as a child process on a local port and restarts it if it dies, unless MODEL_URL points at one already running.
 * The demo station has no sensors, so it sends recorded sample captures (model_service/samples), in turn.
 */
const SERVICE_DIR = path.join(__dirname, '..', '..', 'model_service');
const SAMPLE_DIR = path.join(SERVICE_DIR, 'samples');
const PORT = Number(process.env.MODEL_PORT) || 8001;
const URL = process.env.MODEL_URL || `http://127.0.0.1:${PORT}`;

function pythonPath() {
  if (process.env.MODEL_PYTHON) return process.env.MODEL_PYTHON;
  const venv = path.join(SERVICE_DIR, '..', 'reasoning_model', '.venv');
  // macOS/Linux venvs keep python in bin/, Windows ones in Scripts\
  for (const python of [path.join(venv, 'bin', 'python'), path.join(venv, 'Scripts', 'python.exe')]) {
    if (fs.existsSync(python)) return python;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function start() {
  if (process.env.MODEL_URL) return;
  const child = spawn(pythonPath(), [path.join(SERVICE_DIR, 'serve.py')], {
    env: { ...process.env, MODEL_PORT: String(PORT) },
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  child.on('exit', (code) => {
    console.warn(`Model service exited (${code}); restarting in 3 s`);
    setTimeout(start, 3000);
  });
  process.once('exit', () => child.kill());
}

// stop the model with the server: Ctrl+C or Render's SIGTERM would otherwise leave it holding its port
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => process.exit(0));

const samples = fs
  .readdirSync(SAMPLE_DIR)
  .filter((f) => f.endsWith('.json'))
  .sort()
  .map((f) => JSON.parse(fs.readFileSync(path.join(SAMPLE_DIR, f), 'utf8')));
let next = 0;

/** The next recorded capture, round-robin, so a demo shows both a low- and a high-load result. */
function nextSample() {
  const sample = samples[next % samples.length];
  next += 1;
  return sample;
}

/** Sends one capture to the model; resolves to its output and the transfer details. */
async function predict(sample) {
  const body = JSON.stringify({ subject: sample.subject, windows: sample.windows });
  const started = Date.now();
  const response = await fetch(`${URL}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal: AbortSignal.timeout(30000),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `Model service answered ${response.status}`);
  return { result, bytes: Buffer.byteLength(body), modelMs: Date.now() - started };
}

async function health() {
  try {
    const response = await fetch(`${URL}/health`, { signal: AbortSignal.timeout(3000) });
    return response.ok ? await response.json() : { ok: false };
  } catch {
    return { ok: false };
  }
}

module.exports = { start, nextSample, predict, health, pythonPath };
