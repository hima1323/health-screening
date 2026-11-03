import styles from './StatusPill.module.css';
import usePrefs from '../../../hooks/usePrefs';

const TONE_BY_STATUS = {
  optimal: 'ok',
  'optimal range': 'ok',
  stable: 'ok',
  cleared: 'ok',
  normal: 'ok',
  'not normal': 'warn',
  good: 'ok',
  'sensors ready': 'ok',
  capturing: 'warn',
  analysing: 'warn',
  'conditional step': 'warn',
  'slightly elevated': 'warn',
  'mild fever': 'warn',
  flagged: 'crit',
  watch: 'warn',
  fair: 'warn',
  poor: 'crit',
  'needs attention': 'crit',
  review: 'warn',
  'above range': 'warn',
  'below range': 'warn',
  'low mental load': 'ok',
  'high mental load': 'warn',
  // the reasoning model's triage levels
  urgent: 'crit',
  'see a doctor soon': 'warn',
  'self-care': 'ok',
  remeasure: 'warn',
  linked: 'warn',
  uploading: 'warn',
  done: 'ok',
  failed: 'crit',
};

/** A status chip whose colour is carried by the dot rather than a tinted box. */
export default function StatusPill({ children, dot = true, className = '' }) {
  const { t } = usePrefs();
  const tone = TONE_BY_STATUS[String(children).toLowerCase()];
  return (
    <span className={`${styles.pill} ${tone ? styles[tone] : ''} ${className}`.trim()}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {t(children)}
    </span>
  );
}
