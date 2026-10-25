require('dotenv').config();
const path = require('path');
const express = require('express');
const cors = require('cors');
const connectDB = require('./db');
const apiRouter = require('./routes/api');
const authRouter = require('./routes/auth');
const doctorRouter = require('./routes/doctor');

const app = express();
app.use(cors());
app.use(express.json());
app.use('/api/auth', authRouter);
app.use('/api/doctor', doctorRouter);
app.get('/api/health', (req, res) => res.json({ ok: true }));
app.use('/api', apiRouter);

// the built client (npm run build in client/), so one deploy serves app + API
const CLIENT_DIST = path.join(__dirname, '..', 'client', 'dist');
app.use(express.static(CLIENT_DIST));
app.get(/^(?!\/api\/).*/, (req, res) => res.sendFile(path.join(CLIENT_DIST, 'index.html')));

const PORT = process.env.PORT || 4000;

// Render's free tier sleeps after 15 min without traffic; ping our own public URL
// every 5 min to keep it awake. RENDER_EXTERNAL_URL is set by Render, unset locally.
function keepAwake(url) {
  setInterval(() => {
    fetch(`${url}/api/health`).catch((err) => console.warn('Keep-awake ping failed:', err.message));
  }, 5 * 60 * 1000);
}

connectDB()
  .then(() => {
    app.listen(PORT, () => console.log(`Aura Screen API listening on port ${PORT}`));
    if (process.env.RENDER_EXTERNAL_URL) keepAwake(process.env.RENDER_EXTERNAL_URL);
  })
  .catch((err) => {
    console.error('Failed to connect to MongoDB', err);
    process.exit(1);
  });
