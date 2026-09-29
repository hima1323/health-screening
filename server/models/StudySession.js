const mongoose = require('mongoose');

/*
 * One recorded study session from a public dataset — built by
 * analysis/build_sessions.py and loaded by the seed script. Distinct from
 * ScreeningSession, which is a live capture at a station.
 */

const phaseSchema = new mongoose.Schema(
  {
    name: { type: String, required: true },
    startS: { type: Number, required: true },
    endS: { type: Number, required: true },
    // true when this phase was recorded separately from the one before it
    discontinuous: { type: Boolean, default: false },
    note: String,
  },
  { _id: false }
);

/** One signal on the session clock. Tracks sharing a `group` are drawn on one row. */
const trackSchema = new mongoose.Schema(
  {
    key: { type: String, required: true },
    group: { type: String, required: true },
    label: { type: String, required: true },
    unit: String,
    fs: { type: Number, required: true, min: 0 },
    values: { type: [Number], default: [] },
  },
  { _id: false }
);

const metricDefSchema = new mongoose.Schema(
  {
    key: { type: String, required: true },
    label: { type: String, required: true },
    unit: String,
    digits: { type: Number, default: 1 },
    lowerIsBetter: { type: Boolean, default: false },
  },
  { _id: false }
);

const fusionPartSchema = new mongoose.Schema(
  { key: String, label: String, reading: String, points: { type: Number, default: null } },
  { _id: false }
);

const pipelineStageSchema = new mongoose.Schema(
  {
    stage: { type: String, required: true },
    modality: { type: String, default: 'all' },
    detail: String,
    status: { type: String, enum: ['ok', 'degraded', 'skipped'], default: 'ok' },
    ms: { type: Number, default: null },
  },
  { _id: false }
);

const studySessionSchema = new mongoose.Schema(
  {
    sessionKey: { type: String, required: true, unique: true },
    source: { dataset: String, kind: String, url: String, note: String },
    subject: { id: String, age: Number, sex: String, bmi: Number },
    label: { type: String, required: true },
    recordedOn: String,
    durationS: Number,
    modalities: [{ _id: false, key: String, label: String, detail: String }],
    phases: { type: [phaseSchema], default: [] },
    tracks: { type: [trackSchema], default: [] },
    metricDefs: { type: [metricDefSchema], default: [] },
    // per phase: { phase, values: { metricKey: number | null } }
    metrics: [{ _id: false, phase: String, values: { type: Map, of: Number } }],
    quality: { status: String, message: String },
    fusion: {
      title: String,
      method: String,
      score: { type: Number, default: null },
      scoreMax: { type: Number, default: null },
      band: String,
      verdict: String,
      stats: [{ _id: false, label: String, value: String, hint: String }],
      parts: { type: [fusionPartSchema], default: [] },
      note: String,
    },
    pipeline: { type: [pipelineStageSchema], default: [] },
  },
  { timestamps: true }
);

module.exports = mongoose.model('StudySession', studySessionSchema);
