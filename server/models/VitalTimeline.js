const mongoose = require('mongoose');

/** One reading from one modality at one point in time. `value: null` = it did not run. */
const sampleSchema = new mongoose.Schema(
  { label: String, value: { type: Number, default: null }, baseline: Number },
  { _id: false }
);

/**
 * One sensing channel — camera-derived pulse, thermal, or contact ECG.
 * `quality` is the mean per-sample signal quality the pipeline reported, 0–1,
 * and is what the fusion step weights each channel by.
 */
const modalitySchema = new mongoose.Schema(
  {
    key: { type: String, enum: ['rppg', 'thermal', 'ecg'], required: true },
    label: { type: String, required: true },
    unit: String,
    source: String,
    quality: { type: Number, min: 0, max: 1 },
    samples: [sampleSchema],
    note: String,
  },
  { _id: false }
);

/** What the channels say once combined, and how much they agreed. */
const fusionSchema = new mongoose.Schema(
  {
    index: Number,
    verdict: String,
    confidence: { type: Number, min: 0, max: 1 },
    agreement: { type: Number, min: 0, max: 1 },
    method: String,
    contributions: [{ _id: false, key: String, weight: Number, reading: String, deviation: Number }],
    note: String,
  },
  { _id: false }
);

/** One step of the preprocessing chain, in the order it runs. */
const pipelineStageSchema = new mongoose.Schema(
  {
    stage: { type: String, required: true },
    modality: { type: String, default: 'all' },
    detail: String,
    status: { type: String, enum: ['ok', 'degraded', 'skipped'], default: 'ok' },
    ms: Number,
  },
  { _id: false }
);

const vitalTimelineSchema = new mongoose.Schema({
  patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient', required: true },
  exportedDate: String,
  meanPulse: Number,
  thermalAvg: Number,
  curve: [{ _id: false, label: String, pulse: Number, baseline: Number }],

  modalities: { type: [modalitySchema], default: [] },
  fusion: { type: fusionSchema, default: undefined },
  pipeline: { type: [pipelineStageSchema], default: [] },
});

module.exports = mongoose.model('VitalTimeline', vitalTimelineSchema);
