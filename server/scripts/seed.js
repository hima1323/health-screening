require('dotenv').config();
const connectDB = require('../db');
const Patient = require('../models/Patient');
const Station = require('../models/Station');
const ScreeningSession = require('../models/ScreeningSession');
const Report = require('../models/Report');
const VitalTimeline = require('../models/VitalTimeline');
const ScreeningLog = require('../models/ScreeningLog');
const User = require('../models/User');

async function seed() {
  await connectDB();

  await Promise.all([
    Patient.deleteMany({}),
    Station.deleteMany({}),
    ScreeningSession.deleteMany({}),
    Report.deleteMany({}),
    VitalTimeline.deleteMany({}),
    ScreeningLog.deleteMany({}),
    // user accounts point at a patient record, so they are reset alongside the demo data
    User.deleteMany({}),
  ]);

  const patient = await Patient.create({
    name: 'Ramesh',
    age: 54,
    aura: {
      status: 'optimal',
      state: 'Neutral',
      label: 'READY',
      calmPct: 78,
      groundedPct: 22,
      note: 'Facial micro-pulse and breath cadence sensors are primed for a contactless read at Station 2.',
    },
    consent: {
      givenDate: '12 Aug 2026',
      locations: ['Central Diagnostic Centre', 'Northside Clinic'],
      text:
        'Consent given 12 Aug 2026 for contactless screening at Central Diagnostic Centre and Northside Clinic. Withdraw mid-session and nothing is written; revoke later in Profile and records are deleted within 24 hours.',
    },
  });

  await Station.create({
    stationId: 'station-2',
    captures: [
      {
        icon: 'video',
        title: 'Face video',
        description: 'Processed on the station itself. Never stored.',
      },
      {
        icon: 'thermal',
        title: 'Thermal image',
        description: 'One frame, retained for 90 days.',
      },
      {
        icon: 'ecg',
        title: 'ECG trace — optional',
        description: 'Only when the contactless signal is weak.',
      },
    ],
  });

  await ScreeningSession.create({
    sessionId: 'S-8841',
    patientId: patient._id,
    stationId: 'station-2',
    status: 'Capturing',
    steps: ['Positioning', 'Capturing', 'ECG', 'Analysing'],
    currentStepIndex: 1,
    progress: {
      secondsRemaining: 25,
      phase: 'DEEP CALM',
      instruction: 'Breathe gently, face forward',
      note: 'Keep your expression relaxed inside the illuminated halo. No numbers are shown until the capture completes.',
    },
    environment: {
      lighting: 'Optimal · 480 lx',
      position: 'Centered aura',
      motion: 'Calibrated · still',
      sensorStream: 'Signal 99.4%',
    },
    ecgFallback: {
      title: 'ECG fallback',
      description:
        'if the contactless signal stays weak, the session asks for both index fingers on the station pads for 20 seconds.',
      badge: 'Conditional step',
    },
  });

  await Report.create({
    sessionId: 'S-8841',
    patientId: patient._id,
    nurseCheck: {
      queueId: 'A-14',
      message:
        'A triage nurse will review your readings before your consultation. Two values are outside the normal range for age 54 — this is not a diagnosis.',
      reviewTime: 'about 4 min',
      room: 'Consulting room 4',
    },
    heartRate: {
      value: 112,
      status: 'Slightly elevated',
      resting: 72,
      peak: 118,
      variability: 'Good',
      note:
        'Faster than usual for you at rest. Often caused by stress, fever or recent activity. Normal range 72–96 bpm.',
      normalRange: '72–96 bpm',
    },
    bodyTemp: {
      value: 38.4,
      status: 'Mild fever',
      note: '+1.2 °C above your baseline. Staff will confirm with a second device. Normal 36.1–37.5 °C.',
      normalRange: '36.1–37.5 °C',
    },
    respiration: {
      value: 18,
      status: 'Optimal',
      note: 'Even rhythmic flow, within the expected range for your age. Normal 12–20 /min.',
      normalRange: '12–20 /min',
    },
    shareCode: '894-DXK',
    encryptionNote: 'Encrypted clinical transmission · HIPAA & GDPR certified',
  });

  await VitalTimeline.create({
    patientId: patient._id,
    exportedDate: '08 Sep 2026',
    meanPulse: 74,
    thermalAvg: 36.7,
    curve: [
      { label: '30d ago', pulse: 72, baseline: 74 },
      { label: '23d ago', pulse: 74, baseline: 74 },
      { label: '15d ago', pulse: 80, baseline: 74 },
      { label: '7d ago', pulse: 76, baseline: 74 },
      { label: 'Today', pulse: 112, baseline: 74 },
    ],
  });

  await ScreeningLog.create([
    {
      patientId: patient._id,
      type: 'Contactless scan',
      dateLabel: 'Today · 14:32',
      timeLabel: '09:41',
      location: 'Central Diagnostic Centre · Station 2',
      heartRate: 118,
      temp: 38.4,
      status: 'Flagged',
      clinicianDirective:
        'Elevated thermal reading and tachycardia detected. Proceed to Bay 4 for manual verification and acoustic pulmonary triage.',
      occurredAt: new Date('2026-09-08T14:32:00'),
    },
    {
      patientId: patient._id,
      type: 'Contactless scan',
      dateLabel: '12 Aug · Routine check',
      timeLabel: '02:15 PM',
      location: 'Main lobby sensor',
      heartRate: 72,
      temp: 36.6,
      status: 'Cleared',
      clinicianDirective: '',
      occurredAt: new Date('2026-08-12T14:15:00'),
    },
  ]);

  console.log('Seed complete. Patient id:', patient._id.toString());
  process.exit(0);
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
