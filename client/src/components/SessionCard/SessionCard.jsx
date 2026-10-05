import { Link } from 'react-router-dom';
import { ChevronRight, Stethoscope } from 'lucide-react';
import SignalSketch from '../SignalSketch';
import styles from './SessionCard.module.css';

const seconds = (s) => (s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${Math.round(s)} s`);

/** One past session: when, its id, what was recorded, a sketch of all of it, and whether to see a doctor. */
export default function SessionCard({ session }) {
  const { sessionKey, label, durationS, modalities, preview = [], assessment, recordedOn } = session;
  const advice = assessment?.advice;

  return (
    <Link to={`/timeline/${sessionKey}`} className={styles.card}>
      <div className={styles.top}>
        <div className={styles.titles}>
          <p className={styles.label}>
            {formatDate(recordedOn)}
            <span className={styles.sessionId}>{sessionId(sessionKey)}</span>
          </p>
          <p className={styles.meta}>
            {label} · {seconds(durationS)}
          </p>
        </div>
        <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
      </div>

      {preview.length > 0 && <SignalSketch tracks={preview} laneHeight={9} gap={3} />}

      <div className={styles.chips}>
        {modalities.map((m) => (
          <span
            key={m.key}
            className={`${styles.chip} ${m.simulated ? styles.simulated : ''}`.trim()}
            title={m.simulated ? 'Simulated for the prototype' : undefined}
          >
            {m.label}
            {m.simulated && <em> sim</em>}
          </span>
        ))}
      </div>

      {advice && (
        <p className={`${styles.advice} ${styles[advice.level]}`}>
          <Stethoscope size={13} aria-hidden="true" />
          <span>Doctor:</span> <strong>{advice.answer}</strong>
        </p>
      )}
    </Link>
  );
}

/** "2023-11-13" → "13 Nov 2023". */
export function formatDate(isoDate) {
  if (!isoDate) return 'Date not recorded';
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(isoDate));
}

/** The id a session is known by: "mcd-1020" → "MCD-1020". */
export function sessionId(key) {
  return key.toUpperCase();
}
