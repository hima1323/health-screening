import { trackScale } from './doctor';
import styles from './RangeTrack.module.css';

/**
 * A reading as a dot on a track, over the shaded band of its normal range — out of range turns the dot rose.
 * `size="lg"` adds the band's edges beneath. Renders nothing when the range can't be read.
 */
export default function RangeTrack({ value, normalRange, unit = '', size = 'sm' }) {
  const t = trackScale(value, normalRange);
  if (!t) return null;
  const out = t.position !== 'within';

  return (
    <div className={`${styles.wrap} ${styles[size]}`}>
      <div className={styles.track} role="img" aria-label={`${value} ${unit}, normal ${t.low}–${t.high}`.replace(/\s+,/, ',')}>
        <span className={styles.band} style={{ left: `${t.from}%`, width: `${t.to - t.from}%` }} />
        <span className={`${styles.dot} ${out ? styles.out : ''}`.trim()} style={{ left: `${t.at}%` }} />
      </div>
      {size === 'lg' && (
        <div className={styles.edges} aria-hidden="true">
          <span style={{ left: `${t.from}%` }}>{t.low}</span>
          <span style={{ left: `${t.to}%` }}>{t.high}</span>
        </div>
      )}
    </div>
  );
}
