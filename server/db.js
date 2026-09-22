const mongoose = require('mongoose');

const LOCAL_URI = 'mongodb://127.0.0.1:27017/aura_screen';

/** The host and database, with any credentials stripped — safe to print. */
function describe(uri) {
  try {
    const parsed = new URL(uri);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch {
    return '(unparsable connection string)';
  }
}

async function connectDB() {
  const uri = process.env.MONGODB_URI || LOCAL_URI;

  // buffered queries would hide a bad connection string behind a 10s timeout
  mongoose.set('bufferCommands', false);
  await mongoose.connect(uri, { serverSelectionTimeoutMS: 15000 });

  console.log('MongoDB connected:', describe(uri));
}

module.exports = connectDB;
