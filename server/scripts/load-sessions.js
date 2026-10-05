require('dotenv').config();
const fs = require('fs');
const path = require('path');
const mongoose = require('mongoose');
const connectDB = require('../db');
const StudySession = require('../models/StudySession');

const SESSION_DIR = path.join(__dirname, '..', 'data', 'sessions');
// hand-written, so a rebuild of the sessions never overwrites it
const REASONING_FILE = path.join(__dirname, '..', 'data', 'reasoning.json');

/**
 * Replace the study sessions with the files analysis/build_sessions.py wrote,
 * each with its reasoning from data/reasoning.json.
 * Touches nothing else — user accounts and the demo patient are left alone.
 */
async function loadSessions() {
  const files = fs.existsSync(SESSION_DIR) ? fs.readdirSync(SESSION_DIR).filter((f) => f.endsWith('.json')) : [];
  const reasoning = fs.existsSync(REASONING_FILE) ? JSON.parse(fs.readFileSync(REASONING_FILE, 'utf8')) : {};
  const sessions = files.map((file) => {
    const { id, ...session } = JSON.parse(fs.readFileSync(path.join(SESSION_DIR, file), 'utf8'));
    return { sessionKey: id, ...session, reasoning: reasoning[id] };
  });
  await StudySession.deleteMany({});
  await StudySession.insertMany(sessions);
  return sessions.length;
}

module.exports = loadSessions;

// `npm run sessions` — reload after rebuilding, without signing anyone out
if (require.main === module) {
  connectDB()
    .then(loadSessions)
    .then((count) => console.log(`Study sessions loaded: ${count}`))
    .catch((err) => {
      console.error(err);
      process.exitCode = 1;
    })
    .finally(() => mongoose.disconnect());
}
