import styles from './StatusPill.module.css';

const TONE_BY_STATUS = {
  optimal: 'ok',
  'optimal range': 'ok',
  stable: 'ok',
  cleared: 'ok',
  normal: 'ok',
  good: 'ok',
  'sensors ready': 'ok',
  capturing: 'warn',
  analysing: 'warn',
  'conditional step': 'warn',
  'slightly elevated': 'warn',
  'mild fever': 'warn',
  flagged: 'crit',
};

/** A status chip whose colour is carried by the dot rather than a tinted box. */
export default function StatusPill({ children, dot = true, className = '' }) {
  const tone = TONE_BY_STATUS[String(children).toLowerCase()];
  return (
    <span className={`${styles.pill} ${tone ? styles[tone] : ''} ${className}`.trim()}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}
