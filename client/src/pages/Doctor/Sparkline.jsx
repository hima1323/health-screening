const W = 260;
const H = 70;
const P = 10;

/**
 * A measure across reports, oldest to newest: a line over the shaded normal band,
 * each point rose when it fell out of range. `points` is [{ value, low, high }].
 */
export default function Sparkline({ points, label }) {
  const { low, high } = points[points.length - 1];
  const span = high - low || 1;
  const values = points.map((p) => p.value);
  const min = Math.min(low - span * 0.4, ...values);
  const max = Math.max(high + span * 0.4, ...values);
  const y = (v) => P + (1 - (v - min) / (max - min)) * (H - 2 * P);
  // a single report sits in the middle rather than on the left edge
  const x = (i) => (points.length === 1 ? W / 2 : P + (i / (points.length - 1)) * (W - 2 * P));
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)} ${y(p.value)}`).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label}>
      <rect x="0" y={y(high)} width={W} height={y(low) - y(high)} rx="4" fill="rgba(109, 143, 173, 0.2)" />
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(p.value)}
          r="5"
          fill={p.value < p.low || p.value > p.high ? 'var(--rose-deep)' : 'var(--calm)'}
          stroke="var(--on-ink)"
          strokeWidth="2"
        />
      ))}
    </svg>
  );
}
