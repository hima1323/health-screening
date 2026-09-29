import { GitMerge } from 'lucide-react';
import { StatusPill, IconBadge } from '../ui';
import styles from './FusionPanel.module.css';

/**
 * What the channels say together.
 *
 * Every session describes its own fusion — NEWS2 for the clinical sittings,
 * an arousal vote for the drive — so this renders whatever parts it is given:
 * each input, its reading, and the points it contributed.
 */
export default function FusionPanel({ fusion }) {
  const { title, method, score, scoreMax, band, verdict, stats = [], parts = [], note } = fusion;
  const scored = score !== null && score !== undefined;

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <IconBadge tone="rose">
          <GitMerge size={17} strokeWidth={1.7} />
        </IconBadge>
        <div className={styles.headText}>
          <p className="label tight">{title}</p>
          <p className={styles.method}>{method}</p>
        </div>
        <StatusPill>{verdict}</StatusPill>
      </div>

      <div className={styles.scores}>
        <div className={styles.score}>
          <p className={`numeral ${styles.big}`}>
            {scored ? score : '—'}
            {scored && scoreMax && <span className={styles.of}> / {scoreMax}</span>}
          </p>
          <p className="label tight">{band}</p>
        </div>
        {stats.map((s) => (
          <div key={s.label} className={styles.score} title={s.hint}>
            <p className={styles.stat}>{s.value}</p>
            <p className="label tight">{s.label}</p>
          </div>
        ))}
      </div>

      <ul className={styles.parts}>
        {parts.map((p) => (
          <li key={p.key}>
            <span className={styles.partLabel}>{p.label}</span>
            <span className={styles.reading}>{p.reading}</span>
            {p.points !== null && p.points !== undefined && (
              <span className={`${styles.points} ${p.points > 0 ? styles.hot : ''}`.trim()}>
                {p.points > 0 ? `+${p.points}` : '0'}
              </span>
            )}
          </li>
        ))}
      </ul>

      <p className="muted">{note}</p>
    </div>
  );
}
