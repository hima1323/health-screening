import { Stethoscope, HeartPulse } from 'lucide-react';
import { IconBadge } from '../ui';
import styles from './AssessmentPanel.module.css';

/** The conclusion a patient actually needs: what the readings add up to, and whether to see a doctor. */
export default function AssessmentPanel({ assessment }) {
  const { condition, findings = [], advice, disclaimer } = assessment;

  return (
    <div className={styles.panel}>
      <div className={`${styles.advice} ${styles[advice.level]}`}>
        <Stethoscope size={20} strokeWidth={1.7} aria-hidden="true" />
        <div>
          <p className={styles.question}>Should you contact a doctor?</p>
          <p className={styles.answer}>{advice.answer}</p>
          <p className={styles.adviceText}>{advice.text}</p>
        </div>
      </div>

      <div className={styles.block}>
        <div className={styles.blockHead}>
          <IconBadge tone="rose">
            <HeartPulse size={16} strokeWidth={1.7} />
          </IconBadge>
          <p className="label tight">Condition</p>
        </div>
        <p className={styles.headline}>{condition}</p>
      </div>

      <ul className={styles.findings}>
        {findings.map((f) => (
          <li key={f.label}>
            <span className={`${styles.dot} ${styles[`tone_${f.tone}`]}`} aria-hidden="true" />
            <div>
              <p className={styles.findingLabel}>{f.label}</p>
              <p className="muted small">{f.detail}</p>
            </div>
          </li>
        ))}
      </ul>

      <p className={styles.disclaimer}>{disclaimer}</p>
    </div>
  );
}
