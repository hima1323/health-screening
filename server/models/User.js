const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
const SALT_ROUNDS = 12;

/** A report the patient uploaded — the bytes live on disk, the metadata here. */
const pastReportSchema = new mongoose.Schema(
  {
    label: { type: String, trim: true, maxlength: 120 },
    originalName: { type: String, required: true, trim: true },
    storedName: { type: String, required: true },
    mimeType: { type: String, required: true },
    sizeBytes: { type: Number, required: true, min: 0 },
  },
  { timestamps: { createdAt: 'uploadedAt', updatedAt: false } }
);

/** The health details collected during onboarding. */
const profileSchema = new mongoose.Schema(
  {
    fullName: { type: String, required: true, trim: true, minlength: 2, maxlength: 80 },
    age: { type: Number, required: true, min: 1, max: 120 },
    sex: { type: String, enum: ['Female', 'Male', 'Intersex', 'Prefer not to say', ''], default: '' },
    phone: { type: String, trim: true, maxlength: 24, default: '' },
    heightCm: { type: Number, min: 30, max: 250 },
    weightKg: { type: Number, min: 2, max: 350 },
    bloodGroup: {
      type: String,
      enum: ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'Unknown', ''],
      default: '',
    },
    conditions: { type: String, trim: true, maxlength: 2000, default: '' },
    medications: { type: String, trim: true, maxlength: 2000, default: '' },
    consentAccepted: {
      type: Boolean,
      required: true,
      validate: { validator: (given) => given === true, message: 'Screening consent is required' },
    },
  },
  { _id: false }
);

const userSchema = new mongoose.Schema(
  {
    name: { type: String, required: [true, 'Name is required'], trim: true, minlength: 2, maxlength: 80 },
    email: {
      type: String,
      required: [true, 'Email is required'],
      unique: true,
      lowercase: true,
      trim: true,
      match: [EMAIL_PATTERN, 'That does not look like an email address'],
    },
    // never returned by a query unless explicitly selected
    // an account created through Google has no password of its own
    passwordHash: {
      type: String,
      select: false,
      required: [
        function needsPassword() {
          return !this.googleId;
        },
        'Password is required',
      ],
    },

    // set when the patient signs in with Google — sparse so password-only accounts don't collide
    googleId: { type: String, unique: true, sparse: true },
    avatarUrl: { type: String, default: '' },

    profile: { type: profileSchema, default: undefined },
    pastReports: { type: [pastReportSchema], default: [] },

    patientId: { type: mongoose.Schema.Types.ObjectId, ref: 'Patient' },
    profileCompletedAt: Date,
    lastSignInAt: Date,
  },
  { timestamps: true }
);

/** Two letters for the avatar, derived rather than stored twice. */
userSchema.virtual('initials').get(function initials() {
  return this.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
});

userSchema.virtual('profileComplete').get(function profileComplete() {
  return Boolean(this.profileCompletedAt);
});

/** Hashes a plaintext password onto the document. */
userSchema.methods.setPassword = async function setPassword(password) {
  this.passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
};

userSchema.methods.verifyPassword = function verifyPassword(password) {
  if (!this.passwordHash) return Promise.resolve(false);
  return bcrypt.compare(password, this.passwordHash);
};

/** The shape the browser is allowed to see — no hash, no internal ids. */
userSchema.methods.toClient = function toClient() {
  return {
    id: this._id,
    name: this.name,
    email: this.email,
    initials: this.initials,
    avatarUrl: this.avatarUrl,
    signedInWith: this.googleId ? 'google' : 'password',
    profile: this.profile || null,
    profileComplete: this.profileComplete,
    pastReports: this.pastReports.map((report) => ({
      id: report._id,
      label: report.label,
      originalName: report.originalName,
      mimeType: report.mimeType,
      sizeBytes: report.sizeBytes,
      uploadedAt: report.uploadedAt,
    })),
    patientId: this.patientId || null,
    createdAt: this.createdAt,
  };
};

module.exports = mongoose.model('User', userSchema);
