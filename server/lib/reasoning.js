const path = require('path');
const { spawn } = require('child_process');
const { pythonPath } = require('./model');

/*
 * The triage demo (routes/triage.js) proxies to reasoning_model's demo service (python -m triage.demo_service).
 * In production (the Docker image) this server starts it as a child process and restarts it if it dies; locally
 * start_aura_demo.bat starts it, or set REASONING_URL to one already running.
 */
const SRC_DIR = path.join(__dirname, '..', '..', 'reasoning_model', 'src');

function start() {
  if (process.env.REASONING_URL || process.env.NODE_ENV !== 'production') return;
  const child = spawn(pythonPath(), ['-m', 'triage.demo_service', '--port', '5055'], {
    cwd: SRC_DIR,
    stdio: ['ignore', 'inherit', 'inherit'],
  });
  child.on('exit', (code) => {
    console.warn(`Reasoning service exited (${code}); restarting in 3 s`);
    setTimeout(start, 3000);
  });
  process.once('exit', () => child.kill());
}

module.exports = { start };
