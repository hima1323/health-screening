import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Minus, Plus, Maximize2 } from 'lucide-react';
import SignalSketch, { envelope, robustRange, TONES } from '../SignalSketch';
import styles from './SyncedTracks.module.css';

// zoom steps in px per second; 60 keeps individual pulse beats and ECG complexes legible
const ZOOMS = [15, 30, 60, 120, 240];
const DEFAULT_ZOOM = 60;
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
  const [pxPerS, setPxPerS] = useState(DEFAULT_ZOOM); // null = fit the whole recording
  const [dragging, setDragging] = useState(false);
  const drag = useRef(null); // { x, left, moved } while the mouse is held on the graph
  const keepCentre = useRef(null); // the time to hold centred across a zoom

  const width = pxPerS === null ? viewWidth : Math.max(viewWidth, Math.round(durationS * pxPerS));
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

  const centreTime = () => {
    const el = scroller.current;
    return ((el.scrollLeft + el.clientWidth / 2) / el.scrollWidth) * durationS;
  };

  const zoom = (next) => {
    keepCentre.current = centreTime();
    setPxPerS(next);
  };
  const fitsWhole = durationS * (pxPerS ?? 0) <= viewWidth;
  const zoomIn = () => zoom(ZOOMS.find((z) => z > (pxPerS ?? viewWidth / durationS)) ?? ZOOMS[ZOOMS.length - 1]);
  const zoomOut = () => {
    const next = [...ZOOMS].reverse().find((z) => z < (pxPerS ?? 0));
    zoom(next === undefined || durationS * next <= viewWidth ? null : next);
  };

  useLayoutEffect(() => {
    const el = scroller.current;
    if (keepCentre.current === null || !el) return;
    el.scrollLeft = (keepCentre.current / durationS) * el.scrollWidth - el.clientWidth / 2;
    keepCentre.current = null;
    syncView();
  }, [width, durationS, syncView]);

  // the wheel listener is attached once, so it reaches the current zoom through a ref
  const zoomRef = useRef({});
  useEffect(() => {
    zoomRef.current = { zoomIn, zoomOut };
  });

  /*
   * Over the graph the wheel moves it sideways; at either end it lets the page
   * scroll on, so the graph never traps you. Pinch — which browsers report as a
   * ctrl-wheel — and ⌘/Ctrl + wheel zoom.
   */
  useEffect(() => {
    const el = scroller.current;
    let pinch = 0;
    const onWheel = (event) => {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        pinch += event.deltaY;
        if (Math.abs(pinch) >= 40) {
          (pinch < 0 ? zoomRef.current.zoomIn : zoomRef.current.zoomOut)();
          pinch = 0;
        }
        return;
      }
      // a sideways trackpad swipe already scrolls the graph natively
      if (Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
      const max = el.scrollWidth - el.clientWidth;
      const atStart = el.scrollLeft <= 0 && event.deltaY < 0;
      const atEnd = el.scrollLeft >= max - 1 && event.deltaY > 0;
      if (max <= 0 || atStart || atEnd) return;
      event.preventDefault();
      el.scrollLeft += event.deltaY * (event.deltaMode === 1 ? 30 : 1);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  /** Mouse drag pans the graph; touch keeps the browser's own swipe. */
  const press = (event) => {
    move(event);
    if (event.pointerType !== 'mouse' || event.button !== 0) return;
    drag.current = { x: event.clientX, left: scroller.current.scrollLeft, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const release = () => {
    drag.current = null;
    setDragging(false);
  };

  const move = (event) => {
    if (drag.current) {
      const dx = event.clientX - drag.current.x;
      if (Math.abs(dx) > 3 && !drag.current.moved) {
        drag.current.moved = true;
        setDragging(true);
      }
      if (drag.current.moved) scroller.current.scrollLeft = drag.current.left - dx;
    }
    const box = surface.current.getBoundingClientRect();
    setCursor(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)) * durationS);
  };

  /** Pressing the overview centres the detail there; dragging keeps it following. */
  const steer = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    const el = scroller.current;
    el.scrollLeft = f * el.scrollWidth - el.clientWidth / 2;
  };
  const steerStart = (event) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    steer(event);
  };
  const steerMove = (event) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) steer(event);
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
      <div className={styles.overview} title="Whole recording — press or drag to move there">
        <div className={styles.overviewInner} onPointerDown={steerStart} onPointerMove={steerMove}>
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
        <span className={styles.toolbar}>
          {scrollable && <span className={styles.hint}>Scroll or drag to move · pinch or ⌘-scroll to zoom</span>}
          <button type="button" className={styles.tool} onClick={zoomOut} disabled={pxPerS === null} aria-label="Zoom out">
            <Minus size={14} />
          </button>
          <button type="button" className={styles.tool} onClick={zoomIn} disabled={pxPerS === ZOOMS[ZOOMS.length - 1]} aria-label="Zoom in">
            <Plus size={14} />
          </button>
          <button
            type="button"
            className={`${styles.tool} ${styles.fit}`}
            onClick={() => zoom(null)}
            disabled={pxPerS === null || fitsWhole}
            aria-label="Show the whole recording"
          >
            <Maximize2 size={13} /> Fit
          </button>
        </span>
      </div>

      <div
        className={styles.scroller}
        ref={scroller}
        onScroll={syncView}
        tabIndex={0}
        aria-label="Signal graph — arrow keys move through the recording"
      >
        <div
          className={`${styles.surface} ${scrollable ? styles.pannable : ''} ${dragging ? styles.dragging : ''}`.trim()}
          ref={surface}
          style={{ width }}
          onPointerMove={move}
          onPointerDown={press}
          onPointerUp={release}
          onPointerCancel={release}
          onPointerLeave={() => !drag.current && setCursor(null)}
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
              // the label on the right edge is right-aligned so it doesn't overhang the graph
              <span key={t} style={{ left: x(t), transform: t / durationS > 0.97 ? 'translateX(-100%)' : undefined }}>
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
