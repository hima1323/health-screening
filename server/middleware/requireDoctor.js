const Doctor = require('../models/Doctor');
const { bearerFrom, readDoctorToken } = require('../lib/token');

/** Resolves a doctor's bearer token to their account and hangs it off the request. */
module.exports = async function requireDoctor(req, res, next) {
  const token = bearerFrom(req);
  const doctorId = token && readDoctorToken(token);
  if (!doctorId) return res.status(401).json({ error: 'Sign in as a doctor to continue' });

  const doctor = await Doctor.findById(doctorId);
  if (!doctor) return res.status(401).json({ error: 'Session expired. Sign in again.' });

  req.doctor = doctor;
  next();
};
