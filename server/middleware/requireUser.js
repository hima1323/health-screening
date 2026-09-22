const User = require('../models/User');
const { bearerFrom, readToken } = require('../lib/token');

/** Resolves the bearer token to a user and hangs it off the request. */
module.exports = async function requireUser(req, res, next) {
  const token = bearerFrom(req);
  const userId = token && readToken(token);
  if (!userId) return res.status(401).json({ error: 'Not signed in' });

  const user = await User.findById(userId);
  if (!user) return res.status(401).json({ error: 'Session expired. Sign in again.' });

  req.user = user;
  next();
};
