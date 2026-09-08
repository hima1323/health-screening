const mongoose = require('mongoose');

const stationSchema = new mongoose.Schema({
  stationId: { type: String, required: true, unique: true },
  captures: [
    {
      icon: String,
      title: String,
      description: String,
    },
  ],
});

module.exports = mongoose.model('Station', stationSchema);
