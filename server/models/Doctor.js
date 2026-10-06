const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const SALT_ROUNDS = 12;

/**
 * A clinician account. There is no public sign-up: clinic staff create doctors
 * (scripts/seed.js for the demo), so a patient can't make themselves one.
 */
const doctorSchema = new mongoose.Schema(
  {
    name: { type: String, required: true, trim: true },
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    // a doctor signs in with Google; the password is only a fallback for the demo account
    passwordHash: { type: String, select: false },
    // set on the doctor's first Google sign-in — sparse so accounts without one don't collide
    googleId: { type: String, unique: true, sparse: true },
    avatarUrl: { type: String, default: '' },
    specialty: { type: String, trim: true, default: '' },
    clinic: { type: String, trim: true, default: '' },
    lastSignInAt: Date,
  },
  { timestamps: true }
);

doctorSchema.methods.setPassword = async function setPassword(password) {
  this.passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
};

doctorSchema.methods.verifyPassword = function verifyPassword(password) {
  if (!this.passwordHash) return Promise.resolve(false);
  return bcrypt.compare(password, this.passwordHash);
};

doctorSchema.methods.toClient = function toClient() {
  return { id: this._id, name: this.name, email: this.email, avatarUrl: this.avatarUrl, specialty: this.specialty, clinic: this.clinic };
};

module.exports = mongoose.model('Doctor', doctorSchema);
