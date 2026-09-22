const { OAuth2Client } = require('google-auth-library');

/*
 * Google Identity Services, ID-token flow:
 * https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
 *
 * The button in the browser gets a signed ID token from Google; the server only
 * has to verify it. No client secret, no redirect, no PKCE state to keep.
 */
const CLIENT_ID = process.env.GOOGLE_CLIENT_ID;

const client = new OAuth2Client(CLIENT_ID);

exports.clientId = CLIENT_ID;
exports.isConfigured = () => Boolean(CLIENT_ID);

/** Verifies Google's signature, issuer and audience, and returns who they say it is. */
exports.verifyCredential = async (credential) => {
  const ticket = await client.verifyIdToken({ idToken: credential, audience: CLIENT_ID });
  const payload = ticket.getPayload();

  if (!payload.email_verified) throw new Error('That Google email address is not verified');

  return {
    googleId: payload.sub,
    email: payload.email,
    name: payload.name || payload.email.split('@')[0],
    avatarUrl: payload.picture || '',
  };
};
