const mongoose = require('mongoose');

const reportSchema = new mongoose.Schema({
  sessionId: { type: String, required: true, unique: true },
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
  recordedAt: Date,
  nurseCheck: {
    queueId: String,
    message: String,
    reviewTime: String,
    room: String,
  },
  heartRate: {
    value: Number,
    status: String,
    resting: Number,
    peak: Number,
    variability: String,
    note: String,
    normalRange: String,
  },
  bodyTemp: {
    value: Number,
    status: String,
    note: String,
    normalRange: String,
  },
  respiration: {
    value: Number,
    status: String,
    note: String,
    normalRange: String,
  },
  shareCode: String,
  encryptionNote: String,
  // an earlier live scan's model output (model_service/serve.py, no longer run): summary, per-window results, sample
  model: mongoose.Schema.Types.Mixed,
  // a live scan's reasoning-model result (reasoning_model triage, lib/reasoning.js): level, rule, readings, card
  reasoning: mongoose.Schema.Types.Mixed,
});

module.exports = mongoose.model('Report', reportSchema);
