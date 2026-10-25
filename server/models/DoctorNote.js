const mongoose = require('mongoose');

/** A doctor's own note on a patient. Only that doctor sees it. */
const doctorNoteSchema = new mongoose.Schema(
  {
    doctorId: { type: mongoose.Schema.Types.ObjectId, ref: 'Doctor', required: true },
    patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
    text: { type: String, required: true, trim: true, maxlength: 2000 },
  },
  { timestamps: true }
);

doctorNoteSchema.index({ doctorId: 1, patientId: 1, createdAt: -1 });

module.exports = mongoose.model('DoctorNote', doctorNoteSchema);
