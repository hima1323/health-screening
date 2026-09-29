import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { StatusPill } from '../ui';
import styles from './SessionCard.module.css';

const seconds = (s) => (s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${Math.round(s)} s`);

/** One past session in the timeline list: what was recorded, and how it read. */
export default function SessionCard({ session }) {
  const { sessionKey, label, subject, durationS, modalities, fusion, quality, source } = session;
  const who = [subject.age && `${subject.age} y`, subject.sex].filter(Boolean).join(' · ');

  return (
    <Link to={`/timeline/${sessionKey}`} className={styles.card}>
      <div className={styles.top}>
        <div className={styles.titles}>
          <p className={styles.label}>{label}</p>
          <p className={styles.meta}>
            {source.dataset} · subject {subject.id}
            {who && ` · ${who}`} · {seconds(durationS)}
          </p>
        </div>
        <StatusPill>{fusion.verdict}</StatusPill>
        <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
      </div>

      <div className={styles.chips}>
        {modalities.map((m) => (
          <span key={m.key} className={styles.chip}>
            {m.label}
          </span>
        ))}
        <span className={styles.quality}>
          <StatusPill dot>{quality.status}</StatusPill>
        </span>
      </div>
    </Link>
  );
}
