const jwt = require('jsonwebtoken');

/*
 * Sessions are stateless JSON Web Tokens. Set JWT_SECRET in .env for anything
 * beyond local development — the fallback below only keeps a fresh checkout running.
 */
const SECRET = process.env.JWT_SECRET || 'aura-screen-development-secret';
const TTL = process.env.JWT_TTL || '30d';

exports.issueToken = (user) => jwt.sign({ sub: user._id.toString() }, SECRET, { expiresIn: TTL });

/** Returns the user id carried by the token, or null when it is missing or expired. */
exports.readToken = (token) => {
  try {
    return jwt.verify(token, SECRET).sub;
  } catch {
    return null;
  }
};

/** Pulls the bearer token out of an Authorization header. */
exports.bearerFrom = (req) => {
  const header = req.get('authorization') || '';
  return header.startsWith('Bearer ') ? header.slice(7).trim() : null;
};
