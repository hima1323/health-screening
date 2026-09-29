import { useMemo, useRef, useState } from 'react';
import styles from './SyncedTracks.module.css';

const W = 600;
const H = 64;
const TONES = ['var(--rose)', 'var(--steel)', 'var(--amber)', 'var(--sage)'];

/** Tracks sharing a `group` share a row and a y-scale, so they can be compared directly. */
function groupTracks(tracks) {
  const rows = [];
  tracks.forEach((track) => {
    const row = rows.find((r) => r.group === track.group);
    if (row) row.tracks.push(track);
    else rows.push({ group: track.group, tracks: [track] });
  });
  return rows.map((row) => {
    const all = row.tracks.flatMap((t) => t.values).filter((v) => v !== null);
    const min = Math.min(...all);
    const max = Math.max(...all);
    return { ...row, min, max: max === min ? min + 1 : max };
  });
}

function pathFor(track, duration, min, max) {
  return track.values
    .map((v, i) => {
      const x = ((i / track.fs) / duration) * W;
      const y = H - ((v - min) / (max - min)) * H;
      return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join('');
}

const fmt = (v, unit) =>
  v === null || v === undefined ? '—' : `${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(unit === 'z' ? 2 : 1)}${unit && unit !== 'z' ? ` ${unit}` : ''}`;

/**
 * Every channel of a session on one time axis.
 *
 * Phase bands sit behind all rows and one crosshair reads every channel at
 * the same instant — the point of the view is that the channels line up, so
 * a change in one can be checked against the others.
 */
export default function SyncedTracks({ tracks, phases, durationS }) {
  const rows = useMemo(() => groupTracks(tracks), [tracks]);
  const tone = (track) => TONES[tracks.indexOf(track) % TONES.length];
  const paths = useMemo(
    () => rows.map((row) => row.tracks.map((t) => pathFor(t, durationS, row.min, row.max))),
    [rows, durationS]
  );
  const [cursor, setCursor] = useState(null); // seconds
  const surface = useRef(null);

  const move = (event) => {
    const box = surface.current.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    setCursor(f * durationS);
  };

  const at = (track) => {
    if (cursor === null) return null;
    const i = Math.min(track.values.length - 1, Math.round(cursor * track.fs));
    return track.values[i];
  };
  const phaseAt = cursor === null ? null : phases.find((p) => cursor >= p.startS && cursor <= p.endS);
  const x = (s) => `${(s / durationS) * 100}%`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * durationS);

  return (
    <div className={styles.wrap}>
      <div
        className={styles.surface}
        ref={surface}
        onPointerMove={move}
        onPointerDown={move}
        onPointerLeave={() => setCursor(null)}
      >
        {/* phase bands and labels, behind every row */}
        <div className={styles.bands} aria-hidden="true">
          {phases.map((p, i) => (
            <div
              key={p.name}
              className={`${styles.band} ${i % 2 ? styles.bandAlt : ''}`.trim()}
              style={{ left: x(p.startS), width: x(p.endS - p.startS) }}
            >
              <span className={styles.bandLabel}>{p.name}</span>
              {p.discontinuous && <span className={styles.break} title="Recorded separately" />}
            </div>
          ))}
        </div>

        {rows.map((row, r) => (
          <div key={row.group} className={styles.row}>
            <svg viewBox={`0 -4 ${W} ${H + 8}`} preserveAspectRatio="none" className={styles.svg} role="img"
              aria-label={row.tracks.map((t) => t.label).join(' and ')}>
              {row.tracks.map((t, i) => (
                <path key={t.key} d={paths[r][i]} className={styles.line} style={{ stroke: tone(t) }} />
              ))}
            </svg>
            <div className={styles.legend}>
              {row.tracks.map((t) => (
                <span key={t.key} className={styles.key}>
                  <i style={{ background: tone(t) }} />
                  {t.label}
                </span>
              ))}
            </div>
          </div>
        ))}

        {cursor !== null && <span className={styles.crosshair} style={{ left: x(cursor) }} aria-hidden="true" />}
      </div>

      <div className={styles.axis} aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} style={{ left: x(t) }}>{t.toFixed(t < 20 ? 1 : 0)} s</span>
        ))}
      </div>

      <div className={styles.readout} aria-live="polite">
        {cursor === null ? (
          <p className="muted small">Move across the tracks to read every channel at the same instant.</p>
        ) : (
          <>
            <p className={styles.readoutHead}>
              {cursor.toFixed(1)} s{phaseAt && ` · ${phaseAt.name}`}
            </p>
            <div className={styles.readoutGrid}>
              {tracks.map((t) => (
                <span key={t.key}>
                  <em>{t.label}</em> {fmt(at(t), t.unit)}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
