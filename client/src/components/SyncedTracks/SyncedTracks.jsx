import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SignalSketch, { envelope, robustRange, TONES } from '../SignalSketch';
import styles from './SyncedTracks.module.css';

// 60 px per second keeps individual pulse beats and ECG complexes legible
const PX_PER_S = 60;
const H = 64;
const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60];

/** Tracks sharing a `group` share a row and a y-scale, so they can be compared directly. */
function groupTracks(tracks) {
  const rows = [];
  tracks.forEach((track) => {
    const row = rows.find((r) => r.group === track.group);
    if (row) row.tracks.push(track);
    else rows.push({ group: track.group, tracks: [track] });
  });
  return rows.map((row) => {
    const [min, max] = robustRange(row.tracks.flatMap((t) => t.values));
    return { ...row, min, max };
  });
}

function pathFor(track, width, duration, min, max) {
  return track.values
    .map((v, i) => {
      const x = (i / track.fs / duration) * width;
      const y = H - ((Math.min(max, Math.max(min, v)) - min) / (max - min)) * H;
      return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join('');
}

const fmt = (v, unit) =>
  v === null || v === undefined
    ? '—'
    : `${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(unit === 'z' || unit === 'mV' ? 2 : 1)}${unit && unit !== 'z' ? ` ${unit}` : ''}`;

/**
 * Every channel of a session on one clock.
 *
 * The overview shows the whole recording for every modality; the detail below
 * scrolls sideways at a fixed time scale so waveforms stay readable however long
 * the session is. One crosshair reads every channel at the same instant.
 */
export default function SyncedTracks({ tracks, phases, durationS }) {
  const scroller = useRef(null);
  const surface = useRef(null);
  const [viewWidth, setViewWidth] = useState(0);
  const [view, setView] = useState({ from: 0, to: 1 }); // visible fraction of the recording
  const [cursor, setCursor] = useState(null); // seconds

  const width = Math.max(viewWidth, Math.round(durationS * PX_PER_S));
  const rows = useMemo(() => groupTracks(tracks), [tracks]);
  const paths = useMemo(
    () => rows.map((row) => row.tracks.map((t) => pathFor(t, width, durationS, row.min, row.max))),
    [rows, width, durationS]
  );
  const overview = useMemo(
    () => tracks.map((t) => ({ key: t.key, label: t.label, ...envelope(t.values, 160) })),
    [tracks]
  );
  const tone = (track) => TONES[tracks.indexOf(track) % TONES.length];

  const syncView = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    setViewWidth(el.clientWidth);
    setView({ from: el.scrollLeft / el.scrollWidth, to: (el.scrollLeft + el.clientWidth) / el.scrollWidth });
  }, []);

  useEffect(() => {
    syncView();
    const observer = new ResizeObserver(syncView);
    observer.observe(scroller.current);
    return () => observer.disconnect();
  }, [syncView]);

  const move = (event) => {
    const box = surface.current.getBoundingClientRect();
    setCursor(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)) * durationS);
  };

  /** Clicking the overview centres the detail on that moment. */
  const jump = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const f = (event.clientX - box.left) / box.width;
    const el = scroller.current;
    el.scrollTo({ left: f * el.scrollWidth - el.clientWidth / 2, behavior: 'smooth' });
  };

  const at = (track) => {
    if (cursor === null) return null;
    return track.values[Math.min(track.values.length - 1, Math.round(cursor * track.fs))];
  };
  const phaseAt = cursor === null ? null : phases.find((p) => cursor >= p.startS && cursor <= p.endS);
  const x = (s) => `${(s / durationS) * 100}%`;
  const step = TICK_STEPS.find((s) => s * (width / durationS) >= 90) ?? 60;
  const ticks = Array.from({ length: Math.floor(durationS / step) + 1 }, (_, i) => i * step);
  const scrollable = width > viewWidth + 1;

  return (
    <div className={styles.wrap}>
      <div className={styles.overview} title="Whole recording — click to jump there">
        <div className={styles.overviewInner} onClick={jump}>
        <div className={styles.overviewPhases} aria-hidden="true">
          {phases.map((p, i) => (
            <span key={p.name} className={i % 2 ? styles.bandAlt : ''} style={{ left: x(p.startS), width: x(p.endS - p.startS) }} />
          ))}
        </div>
        <SignalSketch tracks={overview} laneHeight={11} gap={3} />
        {scrollable && (
          <span
            className={styles.window}
            style={{ left: `${view.from * 100}%`, width: `${(view.to - view.from) * 100}%` }}
            aria-hidden="true"
          />
        )}
        </div>
      </div>
      <div className={styles.overviewKeys}>
        {tracks.map((t) => (
          <span key={t.key} className={styles.key}>
            <i style={{ background: tone(t) }} />
            {t.label}
          </span>
        ))}
        {scrollable && <span className={styles.hint}>Scroll the graph sideways, or click the overview to jump</span>}
      </div>

      <div className={styles.scroller} ref={scroller} onScroll={syncView}>
        <div
          className={styles.surface}
          ref={surface}
          style={{ width }}
          onPointerMove={move}
          onPointerDown={move}
          onPointerLeave={() => setCursor(null)}
        >
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
              <svg
                viewBox={`0 -4 ${width} ${H + 8}`}
                preserveAspectRatio="none"
                className={styles.svg}
                style={{ width }}
                role="img"
                aria-label={row.tracks.map((t) => t.label).join(' and ')}
              >
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

          <div className={styles.axis} aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} style={{ left: x(t) }}>
                {t} s
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.readout} aria-live="polite">
        {cursor === null ? (
          <p className="muted small">Move across the graph to read every channel at the same instant.</p>
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
