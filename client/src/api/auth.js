import { request, post, put, del, setToken } from './client';

/** Which third-party sign-ins the server has credentials for. */
export const getProviders = () => request('/auth/providers');

/** Trades the ID token Google's button produced for one of ours. */
export async function signInWithGoogle(credential) {
  const { token, user } = await post('/auth/google', { credential });
  setToken(token);
  return user;
}

/** Creates an account and stores the session token it returns. */
export async function register({ name, email, password }) {
  const { token, user } = await post('/auth/register', { name, email, password });
  setToken(token);
  return user;
}

/** Signs an existing patient in. */
export async function login({ email, password }) {
  const { token, user } = await post('/auth/login', { email, password });
  setToken(token);
  return user;
}

export const getCurrentUser = () => request('/auth/me').then((r) => r.user);
export const saveProfile = (profile) => put('/auth/me/profile', profile).then((r) => r.user);
export const deletePastReport = (reportId) => del(`/auth/me/reports/${reportId}`).then((r) => r.user);

/** Uploads one or more past reports as multipart form data. */
export function uploadPastReports(files) {
  const form = new FormData();
  Array.from(files).forEach((file) => form.append('reports', file));
  return post('/auth/me/reports', form).then((r) => r.user);
}

export const signOut = () => setToken(null);
