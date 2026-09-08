const mongoose = require('mongoose');

const screeningSessionSchema = new mongoose.Schema({
  sessionId: { type: String, required: true, unique: true },
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
  stationId: { type: String, required: true },
  status: String,
  steps: [String],
  currentStepIndex: Number,
  progress: {
    secondsRemaining: Number,
    phase: String,
    instruction: String,
    note: String,
  },
  environment: {
    lighting: String,
    position: String,
    motion: String,
    sensorStream: String,
  },
  ecgFallback: {
    title: String,
    description: String,
    badge: String,
  },
});

module.exports = mongoose.model('ScreeningSession', screeningSessionSchema);
