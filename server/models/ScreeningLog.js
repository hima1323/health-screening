const mongoose = require('mongoose');

const screeningLogSchema = new mongoose.Schema({
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
  type: String,
  dateLabel: String,
  timeLabel: String,
  location: String,
  heartRate: Number,
  temp: Number,
  status: String,
  clinicianDirective: String,
  occurredAt: { type: Date, default: Date.now },
});

module.exports = mongoose.model('ScreeningLog', screeningLogSchema);
