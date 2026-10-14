import { Stethoscope, HeartPulse } from "lucide-react";
import { IconBadge } from "../ui";
import styles from "./AssessmentPanel.module.css";
import usePrefs from '../../hooks/usePrefs';

/** The conclusion a patient actually needs: what the readings add up to, and whether to see a doctor. */
export default function AssessmentPanel({ assessment }) {
  const { t } = usePrefs();
  const { condition, findings = [], advice, disclaimer } = assessment;

  return (
    <div className={styles.panel}>
      {advice && (
        <div className={`${styles.advice} ${styles[advice.level]}`}>
          <Stethoscope size={20} strokeWidth={1.7} aria-hidden="true" />
          <div>
            <p className={styles.question}>{t('Should you contact a doctor?')}</p>
            <p className={styles.answer}>{t(advice.answer)}</p>
            <p className={styles.adviceText}>{t(advice.text)}</p>
          </div>
        </div>
      )}

      <div className={styles.block}>
        <div className={styles.blockHead}>
          <IconBadge tone="rose">
            <HeartPulse size={16} strokeWidth={1.7} />
          </IconBadge>
          <p className="label tight">{t('Condition')}</p>
        </div>
        <p className={styles.headline}>{t(condition)}</p>
      </div>

      <ul className={styles.findings}>
        {findings.map((f) => (
          <li key={f.label}>
            <span
              className={`${styles.dot} ${styles[`tone_${f.tone}`]}`}
              aria-hidden="true"
            />
            <div>
              <p className={styles.findingLabel}>{t(f.label)}</p>
              <p className="muted small">{t(f.detail)}</p>
            </div>
          </li>
        ))}
      </ul>

      <p className={styles.disclaimer}>{t(disclaimer)}</p>
    </div>
  );
}
