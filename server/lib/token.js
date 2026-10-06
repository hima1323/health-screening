const jwt = require('jsonwebtoken');

/*
 * Sessions are stateless JSON Web Tokens. Set JWT_SECRET in .env for anything
 * beyond local development — the fallback below only keeps a fresh checkout running.
 */
const SECRET = process.env.JWT_SECRET || 'aura-screen-development-secret';
const TTL = process.env.JWT_TTL || '30d';

exports.issueToken = (user) => jwt.sign({ sub: user._id.toString() }, SECRET, { expiresIn: TTL });

/** Returns the patient's user id carried by the token, or null when it is missing, expired or not a patient token. */
exports.readToken = (token) => {
  try {
    const payload = jwt.verify(token, SECRET);
    return payload.aud ? null : payload.sub; // doctor tokens carry an audience; they never open the patient side
  } catch {
    return null;
  }
};

// doctors sign in separately: their tokens name an audience, so neither kind stands in for the other
const DOCTOR_AUDIENCE = 'aura-doctor';
const DOCTOR_TTL = process.env.DOCTOR_JWT_TTL || '12h';

exports.issueDoctorToken = (doctor) =>
  jwt.sign({ sub: doctor._id.toString() }, SECRET, { audience: DOCTOR_AUDIENCE, expiresIn: DOCTOR_TTL });

/** The doctor id in a doctor token, or null. */
exports.readDoctorToken = (token) => {
  try {
    return jwt.verify(token, SECRET, { audience: DOCTOR_AUDIENCE }).sub;
  } catch {
    return null;
  }
};

/** Pulls the bearer token out of an Authorization header. */
exports.bearerFrom = (req) => {
  const header = req.get('authorization') || '';
  return header.startsWith('Bearer ') ? header.slice(7).trim() : null;
};
