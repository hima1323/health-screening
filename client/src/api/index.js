import { request } from './client';

/** Every screen reads from MongoDB through these endpoints. */
export const getPrimary = () => request('/primary');
export const getScanHub = (patientId) => request(`/patients/${patientId}/scan-hub`);
export const getActiveScan = (sessionId) => request(`/sessions/${sessionId}/active-scan`);
export const getReport = (sessionId) => request(`/sessions/${sessionId}/report`);
export const getTimeline = (patientId) => request(`/patients/${patientId}/timeline`);

export * from './auth';
