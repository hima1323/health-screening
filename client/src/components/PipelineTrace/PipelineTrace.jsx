import { Check, TriangleAlert, Minus } from 'lucide-react';
import styles from './PipelineTrace.module.css';

const STATUS_ICON = { ok: Check, degraded: TriangleAlert, skipped: Minus };
const MODALITY_NAME = { rppg: 'Camera', ppg: 'Contact PPG', clinical: 'Clinical', thermal: 'Thermal', ecg: 'ECG', all: 'All channels' };

/**
 * The preprocessing chain a raw frame travels before it reaches fusion.
 *
 * Dimming stages that belong to other channels is the point of `highlight` —
 * selecting a channel above shows which steps produced it.
 */
export default function PipelineTrace({ stages, highlight }) {
  const total = stages.reduce((sum, stage) => sum + (stage.ms || 0), 0);

  return (
    <div className={styles.trace}>
      <ol className={styles.list}>
        {stages.map((stage, index) => {
          const Icon = STATUS_ICON[stage.status];
          const dimmed = highlight && stage.modality !== highlight && stage.modality !== 'all';

          return (
            <li key={stage.stage} className={`${styles.stage} ${dimmed ? styles.dimmed : ''}`.trim()}>
              <span className={styles.rail} aria-hidden="true">
                <span className={`${styles.node} ${styles[stage.status]}`}>
                  <Icon size={11} strokeWidth={2.6} />
                </span>
                {index < stages.length - 1 && <span className={styles.connector} />}
              </span>

              <div className={styles.body}>
                <p className={styles.title}>
                  {stage.stage}
                  <span className={`${styles.tag} ${styles[`tag_${stage.modality}`]}`}>
                    {MODALITY_NAME[stage.modality]}
                  </span>
                  {stage.status === 'degraded' && <span className={styles.warn}>degraded</span>}
                </p>
                <p className={styles.detail}>{stage.detail}</p>
              </div>

              <span className={styles.ms}>{stage.ms === null || stage.ms === undefined ? 'offline' : `${stage.ms} ms`}</span>
            </li>
          );
        })}
      </ol>

      <p className="muted small">
        {stages.length} stages · {Math.round(total)} ms measured
      </p>
    </div>
  );
}
