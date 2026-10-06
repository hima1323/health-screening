const mongoose = require('mongoose');

/**
 * A report a patient shared with a doctor — made the first time the doctor opens it
 * with the patient's code. A doctor's patient list is exactly these records.
 */
const reportShareSchema = new mongoose.Schema(
  {
    doctorId: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor', required: true },
    reportId: { type: mongoose.Schema.Types.ObjectId, ref: 'Report', required: true },
    patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
    lastOpenedAt: { type: Date, default: Date.now },
  },
  { timestamps: { createdAt: 'sharedAt', updatedAt: false } }
);

reportShareSchema.index({ doctorId: 1, reportId: 1 }, { unique: true });

module.exports = mongoose.model('ReportShare', reportShareSchema);
