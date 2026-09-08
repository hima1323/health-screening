const mongoose = require('mongoose');

const patientSchema = new mongoose.Schema({
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
