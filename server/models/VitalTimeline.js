const mongoose = require('mongoose');

const vitalTimelineSchema = new mongoose.Schema({
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
  exportedDate: String,
  meanPulse: Number,
  thermalAvg: Number,
  curve: [
    {
      label: String,
      pulse: Number,
      baseline: Number,
    },
  ],
});

module.exports = mongoose.model('VitalTimeline', vitalTimelineSchema);
