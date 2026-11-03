const mongoose = require('mongoose');

/**
 * One contactless scan, from the moment a phone scans the kiosk QR until the model's answer is a report.
 * `stage` moves linked → capturing → uploading → analysing → done (or failed); each step stamps its time,
 * so the phone and the kiosk can both show where it is.
 */
const scanSchema = new mongoose.Schema(
  {
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
    patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
    stationId: { type: String, required: true },
    stage: {
      type: String,
      enum: ['linked', 'capturing', 'uploading', 'analysing', 'done', 'failed'],
      default: 'linked',
    },
    stages: { type: Map, of: Date, default: {} },
    captureSeconds: Number,
    sample: { key: String, task: String, dataset: String },
    upload: { modelMs: Number },
    sessionId: String, // the report the result became
    error: String,
  },
  { timestamps: true }
);

scanSchema.methods.toClient = function toClient() {
  return {
    id: this._id,
    stationId: this.stationId,
    stage: this.stage,
    stages: Object.fromEntries(this.stages),
    captureSeconds: this.captureSeconds,
    sample: this.sample,
    upload: this.upload,
    sessionId: this.sessionId,
    error: this.error,
  };
};

module.exports = mongoose.model('Scan', scanSchema);
