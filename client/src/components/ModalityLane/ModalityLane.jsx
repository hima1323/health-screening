import { Camera, Thermometer, Activity } from 'lucide-react';
import styles from './ModalityLane.module.css';

const ICONS = { rppg: Camera, thermal: Thermometer, ecg: Activity };

const WIDTH = 240;
const HEIGHT = 46;

/**
 * One sensing channel: its signal against the patient's baseline, the latest
 * reading, and the signal quality the pipeline scored it at.
 *
 * Samples with `value: null` are gaps — the channel did not run at that point —
 * so the line breaks rather than interpolating through missing data.
 */
export default function ModalityLane({ modality, selected = false, onSelect }) {
  const { key, label, unit, source, quality, samples, note } = modality;
  const Icon = ICONS[key];

  const present = samples.filter((s) => s.value !== null);
  const values = present.map((s) => s.value);
  const baselines = samples.map((s) => s.baseline).filter(Boolean);
  const min = Math.min(...values, ...baselines);
  const max = Math.max(...values, ...baselines);
  const span = max - min || 1;

  const x = (index) => (index / (samples.length - 1)) * WIDTH;
  const y = (value) => HEIGHT - ((value - min) / span) * HEIGHT;

  // a gap restarts the path, so a missing sample shows as a break in the line
  const path = samples
    .map((sample, index) => (sample.value === null ? null : `${x(index)},${y(sample.value)}`))
    .reduce((acc, point) => {
      if (!point) return [...acc, null];
      const previous = acc[acc.length - 1];
      return [...acc, `${previous == null ? 'M' : 'L'}${point}`];
    }, [])
    .filter(Boolean)
    .join(' ');

  const latest = present[present.length - 1];
  const coverage = Math.round((present.length / samples.length) * 100);

  return (
    <button
      type="button"
      className={`${styles.lane} ${selected ? styles.selected : ''}`.trim()}
      onClick={() => onSelect?.(key)}
      aria-pressed={selected}
    >
      <div className={styles.head}>
        <span className={`${styles.icon} ${styles[key]}`} aria-hidden="true">
          <Icon size={15} strokeWidth={1.8} />
        </span>
        <div className={styles.titles}>
          <p className={styles.label}>{label}</p>
          <p className={styles.source}>{source}</p>
        </div>
        <p className={styles.reading}>
          <span className="numeral">{latest.value}</span>
          <span className={styles.unit}>{unit}</span>
        </p>
      </div>

      <svg
        className={styles.spark}
        viewBox={`-3 -6 ${WIDTH + 6} ${HEIGHT + 12}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label} trend, latest ${latest.value} ${unit}`}
      >
        <path d={`M0,${y(samples[0].baseline)} L${WIDTH},${y(samples[0].baseline)}`} className={styles.baseline} />
        <path d={path} className={`${styles.line} ${styles[`line_${key}`]}`} />
        {samples.map((sample, index) =>
          sample.value === null ? (
            <circle key={sample.label} cx={x(index)} cy={HEIGHT / 2} r="2" className={styles.gap} />
          ) : (
            <circle
              key={sample.label}
              cx={x(index)}
              cy={y(sample.value)}
              r={index === samples.length - 1 ? 4 : 2.5}
              className={`${styles.dot} ${styles[`dot_${key}`]}`}
            />
          )
        )}
      </svg>

      <div className={styles.meta}>
        <span className={styles.qualityTrack} aria-hidden="true">
          <span className={styles.qualityFill} style={{ width: `${quality * 100}%` }} />
        </span>
        <span className={styles.qualityText}>
          SNR {Math.round(quality * 100)}% · {coverage}% coverage
        </span>
      </div>

      {selected && <p className={styles.note}>{note}</p>}
    </button>
  );
}
