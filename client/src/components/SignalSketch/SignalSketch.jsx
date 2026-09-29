import { TONES, robustRange } from './envelope';
import styles from './SignalSketch.module.css';

const W = 200;

/** One band from an envelope, scaled into its own lane. */
function band({ lo, hi }, top, height) {
  const [min, max] = robustRange([...lo, ...hi]);
  const span = max - min;
  const x = (i) => ((i / Math.max(1, lo.length - 1)) * W).toFixed(1);
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const y = (v) => (top + height - ((clamp(v) - min) / span) * height).toFixed(1);
  const upper = hi.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  const lower = lo.map((v, i) => `L${x(i)},${y(v)}`).reverse().join('');
  return `${upper}${lower}Z`;
}

/**
 * The whole of every track at a glance, one thin lane each.
 * `tracks` are `{ key, label, lo, hi }` envelopes.
 */
export default function SignalSketch({ tracks, laneHeight = 12, gap = 3, className = '' }) {
  const height = tracks.length * (laneHeight + gap) - gap;
  return (
    <svg
      className={`${styles.sketch} ${className}`.trim()}
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      style={{ height }}
      role="img"
      aria-label={`Overview of ${tracks.map((t) => t.label).join(', ')}`}
    >
      {tracks.map((t, i) => (
        <path
          key={t.key}
          d={band(t, i * (laneHeight + gap), laneHeight)}
          style={{ fill: TONES[i % TONES.length], stroke: TONES[i % TONES.length] }}
          className={styles.band}
        />
      ))}
    </svg>
  );
}
