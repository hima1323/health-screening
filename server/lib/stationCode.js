const jwt = require('jsonwebtoken');

/*
 * The QR a kiosk shows: "AURA1:" + a short-lived token signed with the server secret.
 * Only this server can make one, so the app ignores every other QR code — a poster,
 * a menu, or a copy of an expired kiosk code.
 */
const SECRET = process.env.JWT_SECRET || 'aura-screen-development-secret';
const PREFIX = 'AURA1:';
const AUDIENCE = 'aura-station'; // keeps station codes and sign-in tokens from standing in for each other
const TTL_S = 10 * 60;

/** A fresh code for one station, and when it stops working. */
exports.issueStationCode = (stationId) => {
  const token = jwt.sign({ station: stationId }, SECRET, { audience: AUDIENCE, expiresIn: TTL_S });
  return { code: PREFIX + token, expiresAt: new Date(Date.now() + TTL_S * 1000).toISOString() };
};

/** The station id inside a scanned code, or an error message a patient can act on. */
exports.readStationCode = (text) => {
  if (typeof text !== 'string' || !text.startsWith(PREFIX)) {
    return { error: 'This is not an Aura Screen station code. Scan the code on the kiosk screen.' };
  }
  try {
    return { stationId: jwt.verify(text.slice(PREFIX.length), SECRET, { audience: AUDIENCE }).station };
  } catch (err) {
    return {
      error:
        err.name === 'TokenExpiredError'
          ? 'This station code has expired. Scan the code currently on the kiosk screen.'
          : 'This code was not made by an Aura Screen kiosk.',
    };
  }
};
