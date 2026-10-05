import { request, post } from './client';

/** Every screen reads from MongoDB through these endpoints. */
export const getPrimary = () => request('/primary');
export const getScanHub = (patientId) => request(`/patients/${patientId}/scan-hub`);
export const getActiveScan = (sessionId) => request(`/sessions/${sessionId}/active-scan`);
export const getReport = (sessionId) => request(`/sessions/${sessionId}/report`);
export const getStudySessions = () => request('/study-sessions');
export const getStudySession = (key) => request(`/study-sessions/${key}`);
export const getStationCode = (stationId) => request(`/stations/${stationId}/code`);
export const verifyStationCode = (code) => post('/stations/verify', { code });
export const studySessionFramesUrl = (key) => `/api/study-sessions/${key}/frames`;

export * from './auth';
