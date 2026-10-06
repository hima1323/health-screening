import { send } from './client';

/* The doctor side signs in separately from patients, with its own token in its own slot. */
const TOKEN_KEY = 'aura-screen.doctor-token';

export const getDoctorToken = () => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setDoctorToken = (token) => {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing — the session lasts until reload */
  }
};

/** Any doctor request; a 401 means the session is over, so the stale token is dropped. */
async function doctorSend(path, options = {}) {
  try {
    return await send(`/doctor${path}`, { ...options, token: getDoctorToken() });
  } catch (err) {
    if (err.status === 401) setDoctorToken(null);
    throw err;
  }
}

export async function doctorLogin(email, password) {
  const { token, doctor } = await send('/doctor/login', { method: 'POST', body: { email, password }, token: null });
  setDoctorToken(token);
  return doctor;
}

export const getDoctorMe = () => doctorSend('/me');
export const getDoctorPatients = () => doctorSend('/patients');
export const getDoctorReport = (shareCode) => doctorSend(`/reports/${encodeURIComponent(shareCode)}`);

/** Trade Google's ID token for a doctor session — only works for a doctor the clinic registered. */
export async function doctorGoogleLogin(credential) {
  const { token, doctor } = await send('/doctor/google', { method: 'POST', body: { credential }, token: null });
  setDoctorToken(token);
  return doctor;
}
export const getDoctorPatient = (patientId) => doctorSend(`/patients/${encodeURIComponent(patientId)}`);
