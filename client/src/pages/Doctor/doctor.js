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

/** How many patients sit at each triage level, for the worklist filters. */
export function levelCounts(patients) {
  const counts = { all: patients.length, attention: 0, review: 0, stable: 0 };
  patients.forEach((p) => (counts[p.latest.triage.level] += 1));
  return counts;
}

/** One line on why a report sits where it does: "Nurse check requested · heart rate out of range". */
export function triageReason(report) {
  const reason =
    [
      report.nurseCheck?.queueId && `Nurse check requested (queue ${report.nurseCheck.queueId})`,
      report.triage.outOfRange.length > 0 &&
        `${report.triage.outOfRange.map((r) => r.label.toLowerCase()).join(' and ')} out of range`,
    ]
      .filter(Boolean)
      .join(' · ') || (report.triage.level === 'stable' ? 'All readings in range' : 'Marked for review');
  return reason[0].toUpperCase() + reason.slice(1);
}

/**
 * Where a reading and its normal band sit on a track, as percentages: the band fills the middle
 * and the scale reaches 60% of its width past each edge, so near misses and far misses look different.
 */
export function trackScale(value, normalRange) {
  const range = rangePosition(value, normalRange);
  if (!range) return null;
  const span = range.high - range.low || 1;
  const min = range.low - span * 0.6;
  const max = range.high + span * 0.6;
  const pct = (v) => Math.max(2, Math.min(98, ((v - min) / (max - min)) * 100));
  return { ...range, at: pct(value), from: pct(range.low), to: pct(range.high) };
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
