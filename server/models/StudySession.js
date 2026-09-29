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
    simulated: { type: Boolean, default: false },
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
    modalities: [{ _id: false, key: String, label: String, detail: String, simulated: Boolean }],
    // set when part of the session is simulated for the prototype — the UI shows it as a banner
    simulationNote: String,
    phases: { type: [phaseSchema], default: [] },
    tracks: { type: [trackSchema], default: [] },
    // thermogram frames, stored as a file beside the session JSON: one uint8 per pixel,
    // linear from tempMinC to tempMaxC; displayMin/Max is the window the colour map spans
    frames: {
      type: new mongoose.Schema(
        {
          file: { type: String, required: true },
          width: Number,
          height: Number,
          count: Number,
          fps: Number,
          tempMinC: Number,
          tempMaxC: Number,
          displayMinC: Number,
          displayMaxC: Number,
          // per-phase shift added to every pixel — how one shared simulated video serves many sessions
          offsets: [{ _id: false, startS: Number, endS: Number, offsetC: Number }],
          simulated: Boolean,
        },
        { _id: false }
      ),
      default: undefined,
    },
    // regions of interest on the thermogram; `track` names the series each one feeds
    rois: [{ _id: false, key: String, label: String, box: [Number], valid: Boolean, track: String }],
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
    // screening conclusion: the condition and whether to see a doctor
    assessment: {
      condition: String,
      findings: [{ _id: false, label: String, detail: String, tone: { type: String, enum: ['ok', 'warn', 'bad', 'info'] } }],
      advice: {
        level: { type: String, enum: ['ok', 'rescan', 'routine', 'soon', 'urgent', 'na'] },
        answer: String,
        text: String,
      },
      disclaimer: String,
    },
    pipeline: { type: [pipelineStageSchema], default: [] },
  },
  { timestamps: true }
);

module.exports = mongoose.model('StudySession', studySessionSchema);
