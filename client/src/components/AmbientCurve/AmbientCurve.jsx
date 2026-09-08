import styles from './AmbientCurve.module.css';

const WIDTH = 640;
const HEIGHT = 120;
const PADDING = 14;

function buildPath(values, min, max) {
  const step = WIDTH / (values.length - 1);
  return values
    .map((value, index) => {
      const x = index * step;
      const y = HEIGHT - ((value - min) / (max - min || 1)) * HEIGHT;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

/** The 30-day heart-rate trend, with the patient's baseline dashed behind it. */
export default function AmbientCurve({ curve }) {
  const pulses = curve.map((point) => point.pulse);
  const baselines = curve.map((point) => point.baseline);
  const min = Math.min(...pulses, ...baselines) - 5;
  const max = Math.max(...pulses, ...baselines) + 5;

  const step = WIDTH / (curve.length - 1);
  const yFor = (value) => HEIGHT - ((value - min) / (max - min || 1)) * HEIGHT;

  return (
    <div className={styles.curve}>
      <svg
        viewBox={`-${PADDING} -${PADDING} ${WIDTH + PADDING * 2} ${HEIGHT + PADDING * 2}`}
        className={styles.svg}
        preserveAspectRatio="none"
        role="img"
        aria-label="30-day heart rate trend"
      >
        <g className={styles.grid}>
          <path d={`M0 ${HEIGHT * 0.2}H${WIDTH}M0 ${HEIGHT * 0.5}H${WIDTH}M0 ${HEIGHT * 0.8}H${WIDTH}`} />
        </g>
        <path d={buildPath(baselines, min, max)} className={styles.baseline} />
        <path d={buildPath(pulses, min, max)} className={styles.line} />
        {curve.map((point, index) => {
          const isToday = index === curve.length - 1;
          return (
            <circle
              key={point.label}
              cx={index * step}
              cy={yFor(point.pulse)}
              r={isToday ? 6 : 4}
              className={isToday ? styles.today : styles.point}
            />
          );
        })}
      </svg>

      <div className={styles.labels}>
        {curve.map((point) => (
          <span key={point.label}>{point.label.toUpperCase()}</span>
        ))}
      </div>
    </div>
  );
}
