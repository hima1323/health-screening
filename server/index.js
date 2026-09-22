require('dotenv').config();
const express = require('express');
const cors = require('cors');
const connectDB = require('./db');
const apiRouter = require('./routes/api');
const authRouter = require('./routes/auth');

const app = express();
app.use(cors());
app.use(express.json());
app.use('/api/auth', authRouter);
app.use('/api', apiRouter);

const PORT = process.env.PORT || 4000;

connectDB()
  .then(() => {
    app.listen(PORT, () => console.log(`Aura Screen API listening on port ${PORT}`));
  })
  .catch((err) => {
    console.error('Failed to connect to MongoDB', err);
    process.exit(1);
  });
