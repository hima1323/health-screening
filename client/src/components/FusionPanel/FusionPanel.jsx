import { GitMerge } from 'lucide-react';
import { StatusPill, IconBadge } from '../ui';
import styles from './FusionPanel.module.css';

const NAMES = { rppg: 'Camera pulse', thermal: 'Thermal', ecg: 'Contact ECG' };

/**
 * What the channels say once combined.
 *
 * Late fusion: each channel is scored on its own, then the scores are averaged
 * with weights set by signal quality. The bar shows how much of the verdict each
 * channel is responsible for — the point being that no single channel decides.
 */
export default function FusionPanel({ fusion, onSelect, selected }) {
  const { index, verdict, confidence, agreement, method, contributions, note } = fusion;

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <IconBadge tone="rose">
          <GitMerge size={17} strokeWidth={1.7} />
        </IconBadge>
        <div className={styles.headText}>
          <p className="label tight">Fused assessment</p>
          <p className={styles.method}>{method}</p>
        </div>
        <StatusPill>{verdict}</StatusPill>
      </div>

      <div className={styles.scores}>
        <div className={styles.score}>
          <p className={`numeral ${styles.big}`}>{index}</p>
          <p className="label tight">Screening index</p>
        </div>
        <div className={styles.score}>
          <p className={`numeral ${styles.big}`}>{Math.round(confidence * 100)}%</p>
          <p className="label tight">Confidence</p>
        </div>
        <div className={styles.score}>
          <p className={`numeral ${styles.big}`}>{Math.round(agreement * 100)}%</p>
          <p className="label tight">Channel agreement</p>
        </div>
      </div>

      <div className={styles.stack} role="img" aria-label="Contribution of each channel to the fused result">
        {contributions.map((part) => (
          <span
            key={part.key}
            className={`${styles.segment} ${styles[part.key]}`}
            style={{ width: `${part.weight * 100}%` }}
            title={`${NAMES[part.key]} · ${Math.round(part.weight * 100)}%`}
          />
        ))}
      </div>

      <ul className={styles.legend}>
        {contributions.map((part) => (
          <li key={part.key}>
            <button
              type="button"
              className={`${styles.chip} ${selected === part.key ? styles.chipOn : ''}`.trim()}
              onClick={() => onSelect?.(part.key)}
            >
              <span className={`${styles.swatch} ${styles[part.key]}`} aria-hidden="true" />
              <span className={styles.chipName}>{NAMES[part.key]}</span>
              <span className={styles.chipWeight}>{Math.round(part.weight * 100)}%</span>
              <span className={styles.chipReading}>{part.reading}</span>
            </button>
          </li>
        ))}
      </ul>

      <p className="muted">{note}</p>
    </div>
  );
}
