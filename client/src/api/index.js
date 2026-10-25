import { BASE_URL, request, post } from './client';

/** Every screen reads from MongoDB through these endpoints. */
export const getPrimary = () => request('/primary');
export const getScanHub = (patientId) => request(`/patients/${patientId}/scan-hub`);
export const getReport = (sessionId) => request(`/sessions/${sessionId}/report`);
export const getStudySessions = () => request('/study-sessions');
export const getStudySession = (key) => request(`/study-sessions/${key}`);
export const getStationCode = (stationId) => request(`/stations/${stationId}/code`);
export const verifyStationCode = (code) => post('/stations/verify', { code });
export const studySessionFramesUrl = (key) => `${BASE_URL}/study-sessions/${key}/frames`;


export * from './auth';
export * from './doctor';

/** A live scan: start it with the kiosk code the phone scanned, then poll it until the model has answered. */
export const startScan = (code) => post('/scans', { code });
export const getScan = (id) => request(`/scans/${id}`);
export const getStationLive = (stationId) => request(`/stations/${stationId}/live`);
