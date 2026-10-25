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
  // a live scan's model output (model_service/serve.py): summary, per-window results, the sample it read
  model: mongoose.Schema.Types.Mixed,
});

module.exports = mongoose.model('Report', reportSchema);
