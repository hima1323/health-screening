// one colour per track, eight distinct so a four-modality session never repeats one
export const TONES = ['var(--rose)', 'var(--steel)', 'var(--amber)', '#b07aa1', '#8a7fb5', '#4f78a6', '#a8683e', '#6b5876'];

/**
 * Min/max per bucket, the way an audio overview is drawn. Averaging would
 * cancel an oscillating pulse to a flat line; the envelope keeps its shape.
 */
export function envelope(values, buckets = 64) {
  const n = Math.min(buckets, values.length);
  const lo = [];
  const hi = [];
  for (let i = 0; i < n; i += 1) {
    const chunk = values.slice(Math.floor((i * values.length) / n), Math.floor(((i + 1) * values.length) / n));
    lo.push(Math.min(...chunk));
    hi.push(Math.max(...chunk));
  }
  return { lo, hi };
}

/** 1st–99th percentile range, so one artefact spike can't flatten a whole trace. */
export function robustRange(values) {
  const sorted = values.filter((v) => v !== null && Number.isFinite(v)).sort((a, b) => a - b);
  if (!sorted.length) return [0, 1];
  const pick = (q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
  const lo = pick(0.01);
  const hi = pick(0.99);
  return hi > lo ? [lo, hi] : [lo, lo + 1];
}
