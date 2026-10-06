require('dotenv').config();
const connectDB = require('../db');
const Patient = require('../models/Patient');
const Station = require('../models/Station');
const ScreeningSession = require('../models/ScreeningSession');
const Report = require('../models/Report');
const ScreeningLog = require('../models/ScreeningLog');
const User = require('../models/User');
const Doctor = require('../models/Doctor');
const ReportShare = require('../models/ReportShare');
const loadSessions = require('./load-sessions');

// the demo clinician. Sign in at /doctor/login with Google: set DEMO_DOCTOR_EMAIL in .env to
// your own Google address so the clinic "knows" you. The password works with the default email.
const DEMO_DOCTOR = {
  name: 'Dr. Priya Nair',
  email: process.env.DEMO_DOCTOR_EMAIL || 'doctor@aura.test',
  password: 'aura-5e9394ee',
  specialty: 'General medicine',
  clinic: 'Central Diagnostic Centre',
};

async function seed() {
  await connectDB();

  await Promise.all([
    Patient.deleteMany({}),
    Station.deleteMany({}),
    ScreeningSession.deleteMany({}),
    Report.deleteMany({}),
    ScreeningLog.deleteMany({}),
    Doctor.deleteMany({}),
    ReportShare.deleteMany({}),
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
    recordedAt: new Date('2026-09-08T14:32:00'),
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
        'Faster than usual for you at rest — often stress, fever or recent activity. A nurse will recheck it.',
      normalRange: '72–96 bpm',
    },
    bodyTemp: {
      value: 38.4,
      status: 'Mild fever',
      note: 'A mild fever, 1.2 °C above your usual. Staff will confirm with a second thermometer.',
      normalRange: '36.1–37.5 °C',
    },
    respiration: {
      value: 18,
      status: 'Optimal',
      note: 'Steady, even breathing — nothing to do.',
      normalRange: '12–20 /min',
    },
    shareCode: '894-DXK',
    encryptionNote: 'Encrypted clinical transmission · HIPAA & GDPR certified',
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

  // two more patients who shared a report, so the doctor dashboard has a list to triage
  const others = await Patient.create([
    { name: 'Arjun Mehta', age: 41 },
    { name: 'Sara Thomas', age: 29 },
  ]);
  await Report.create([
    {
      sessionId: 'S-8836',
      patientId: others[0]._id,
      recordedAt: new Date('2026-10-03T10:05:00'),
      heartRate: { value: 71, status: 'Normal', note: 'Steady and within range.', normalRange: '60–100 bpm' },
      bodyTemp: { value: 36.8, status: 'Normal', note: 'No sign of fever.', normalRange: '36.1–37.5 °C' },
      respiration: { value: 15, status: 'Optimal', note: 'Even, relaxed breathing.', normalRange: '12–20 /min' },
      shareCode: '512-KMR',
    },
    {
      sessionId: 'S-8839',
      patientId: others[1]._id,
      recordedAt: new Date('2026-10-04T16:40:00'),
      heartRate: { value: 98, status: 'Watch', note: 'Upper edge of normal — recheck after rest.', normalRange: '60–100 bpm' },
      bodyTemp: { value: 37.6, status: 'Watch', note: 'Just above normal — no fever yet.', normalRange: '36.1–37.5 °C' },
      respiration: { value: 19, status: 'Optimal', note: 'Within the normal range.', normalRange: '12–20 /min' },
      shareCode: '307-TQA',
    },
  ]);
  await ScreeningLog.create([
    {
      patientId: others[0]._id,
      type: 'Contactless scan',
      dateLabel: '3 Oct · Routine check',
      location: 'Central Diagnostic Centre · Station 2',
      heartRate: 71,
      temp: 36.8,
      status: 'Cleared',
      occurredAt: new Date('2026-10-03T10:05:00'),
    },
    {
      patientId: others[1]._id,
      type: 'Contactless scan',
      dateLabel: '4 Oct · Walk-in',
      location: 'Main lobby sensor',
      heartRate: 98,
      temp: 37.6,
      status: 'Watch',
      clinicianDirective: 'Borderline temperature. Rescan in 24 hours or sooner if symptoms appear.',
      occurredAt: new Date('2026-10-04T16:40:00'),
    },
  ]);

  // Ramesh's report from his August routine check, shared with the doctor back then
  const earlier = await Report.create({
    sessionId: 'S-8790',
    patientId: patient._id,
    recordedAt: new Date('2026-08-12T14:15:00'),
    heartRate: { value: 72, status: 'Normal', note: 'Steady and within range.', normalRange: '60–100 bpm' },
    bodyTemp: { value: 36.6, status: 'Normal', note: 'No sign of fever.', normalRange: '36.1–37.5 °C' },
    respiration: { value: 16, status: 'Optimal', note: 'Even, relaxed breathing.', normalRange: '12–20 /min' },
    shareCode: '611-RPL',
  });

  // the doctor already has Ramesh (both reports) and Arjun; Sara's code is left to add live
  const { password, ...doctorFields } = DEMO_DOCTOR;
  const doctor = new Doctor(doctorFields);
  await doctor.setPassword(password);
  await doctor.save();
  const reports = await Report.find({ shareCode: { $in: ['894-DXK', '512-KMR'] } });
  await ReportShare.create([
    { doctorId: doctor._id, reportId: earlier._id, patientId: patient._id, sharedAt: new Date('2026-08-12T15:00:00') },
    ...reports.map((r) => ({ doctorId: doctor._id, reportId: r._id, patientId: r.patientId })),
  ]);
  console.log(`Demo doctor: ${DEMO_DOCTOR.email} — Google sign-in, or the password in scripts/seed.js`);

  // accounts survive a reset — point them at the new demo patient so nobody is signed out
  const relinked = await User.updateMany({ patientId: { $ne: null } }, { patientId: patient._id });
  console.log(`Accounts kept: ${await User.countDocuments()} (${relinked.modifiedCount} relinked)`);

  console.log(`Study sessions: ${await loadSessions()}`);

  console.log('Seed complete. Patient id:', patient._id.toString());
  process.exit(0);
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
