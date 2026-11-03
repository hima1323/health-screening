const Patient = require('../models/Patient');

/**
 * The account's own patient record, made on first use from the onboarding details. Older accounts that still
 * point at the shared demo patient get their own record too, so a sign-up never renames someone else.
 */
async function patientFor(user) {
  if (!user.profile?.fullName) return null;

  const owned = user.patientId && (await Patient.findOne({ _id: user.patientId, ownerId: user._id }));
  if (owned) return owned;

  const patient = await Patient.create({
    ownerId: user._id,
    name: user.profile.fullName,
    age: user.profile.age,
    aura: {
      status: 'ready',
      label: 'READY',
      note: 'The station reads pulse, breathing, skin and eye signals without touching you. Scan its QR code to begin.',
    },
    consent: {
      givenDate: new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(
        user.profileCompletedAt || new Date()
      ),
      text: 'Consent given for contactless screening. Withdraw mid-session and nothing is written.',
    },
  });
  user.patientId = patient._id;
  await user.save();
  return patient;
}

module.exports = { patientFor };
