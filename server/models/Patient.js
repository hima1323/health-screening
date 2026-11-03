const mongoose = require('mongoose');

const patientSchema = new mongoose.Schema({
  // the account this record belongs to; the seeded demo patients have none
  ownerId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', index: true },
  name: { type: String, required: true },
  age: { type: Number, required: true },
  aura: {
    status: String,
    state: String,
    label: String,
    calmPct: Number,
    groundedPct: Number,
    note: String,
  },
  consent: {
    givenDate: String,
    locations: [String],
    text: String,
  },
});

module.exports = mongoose.model('Patient', patientSchema);
