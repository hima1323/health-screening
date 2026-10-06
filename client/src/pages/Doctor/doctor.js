import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';

export const normaliseCode = (code) => code.trim().toUpperCase();

/**
 * How urgently a report needs the doctor, from its readings:
 * a nurse check or two readings out of range → attention; one out of range or marked watch → review.
 */
export function triage(report) {
  const outOfRange = RESULTS.filter(({ key }) => {
    const r = report[key];
    const range = r && rangePosition(r.value, r.normalRange);
    return range && range.position !== 'within';
  });
  const watched = RESULTS.some(({ key }) => /watch/i.test(report[key]?.status ?? ''));

  if (report.nurseCheck?.queueId || outOfRange.length >= 2) return { level: 'attention', label: 'Needs attention', rank: 0, outOfRange };
  if (outOfRange.length === 1 || watched) return { level: 'review', label: 'Review', rank: 1, outOfRange };
  return { level: 'stable', label: 'Stable', rank: 2, outOfRange };
}

const time = (r) => new Date(r.recordedAt ?? r.sharedAt).getTime();

/**
 * The /patients response, ready to show: each patient's reports newest first with their triage,
 * and the patients themselves most urgent first (by their latest report), then most recent.
 */
export function buildPatients(raw) {
  return raw
    .map(({ patient, reports }) => {
      const sorted = reports.map((r) => ({ ...r, triage: triage(r) })).sort((a, b) => time(b) - time(a));
      return { patient, reports: sorted, latest: sorted[0] };
    })
    .sort((a, b) => a.latest.triage.rank - b.latest.triage.rank || time(b.latest) - time(a.latest));
}

/** Search box filter: a patient's name or any of their session ids. */
export function matchesSearch(entry, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return entry.patient.name.toLowerCase().includes(q) || entry.reports.some((r) => r.sessionId.toLowerCase().includes(q));
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** The four overview numbers, each with the split its bar shows. */
export function overviewStats(patients, now = Date.now()) {
  const levels = { attention: 0, review: 0, stable: 0 };
  patients.forEach((p) => (levels[p.latest.triage.level] += 1));

  const reports = patients.flatMap((p) => p.reports);
  const recent = reports.filter((r) => now - new Date(r.sharedAt).getTime() <= 30 * DAY_MS).length;

  const attention = patients.filter((p) => p.latest.triage.level === 'attention');
  const nurseChecks = attention.filter((p) => p.latest.nurseCheck?.queueId).length;

  const readings = patients.reduce((n, p) => n + RESULTS.filter(({ key }) => p.latest[key]).length, 0);
  const outOfRange = patients.reduce((n, p) => n + p.latest.triage.outOfRange.length, 0);

  return {
    patients: { total: patients.length, ...levels },
    reports: { total: reports.length, recent, earlier: reports.length - recent },
    attention: { total: attention.length, nurseChecks, other: attention.length - nurseChecks },
    readings: { total: readings, outOfRange, inRange: readings - outOfRange },
  };
}

/** "Arjun Mehta" → "AM", "Dr. Priya Nair" → "PN". */
export const initials = (name) =>
  name
    .replace(/^Dr\.?\s*/i, '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
