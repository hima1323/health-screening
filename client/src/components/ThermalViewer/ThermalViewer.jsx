import { useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { studySessionFramesUrl } from '../../api';
import { TONES } from '../SignalSketch';
import { COLORMAPS, gradientCss } from './colormap';
import styles from './ThermalViewer.module.css';

/**
 * The thermogram itself, after Hans's thermal explorer: every frame in false
 * colour with the ROI boxes on the face, the temperature of any pixel under the
 * pointer, and playback that drives the shared session clock.
 *
 * `time` is that clock in seconds; `onTime` moves it — while playing here, or
 * when the graph below is scrubbed, the two stay on the same frame.
 */
export default function ThermalViewer({ sessionKey, frames: meta, rois, tracks, time, onTime }) {
  const { width: W, height: H, count, fps, tempMinC, tempMaxC, displayMinC, displayMaxC } = meta;
  const duration = count / fps;
  const [pixels, setPixels] = useState(null);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [cmap, setCmap] = useState('inferno');
  const [hover, setHover] = useState(null);
  const canvasRef = useRef(null);
  const clock = useRef(time ?? 0);

  const t = time ?? 0;
  // a simulated session shifts a shared video per phase to its own temperatures
  const offset = meta.offsets?.find((o) => t >= o.startS && t < o.endS)?.offsetC ?? meta.offsets?.at(-1)?.offsetC ?? 0;
  const toC = (b) => tempMinC + (b / 255) * (tempMaxC - tempMinC) + offset;
  const index = Math.min(count - 1, Math.max(0, Math.floor(t * fps)));
  const frame = pixels ? pixels.subarray(index * W * H, (index + 1) * W * H) : null;

  // the file is fetched once; every frame is a view into it
  useEffect(() => {
    let cancelled = false;
    fetch(studySessionFramesUrl(sessionKey))
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error('Could not load the thermal frames'))))
      .then((buffer) => {
        if (cancelled) return;
        if (buffer.byteLength < count * W * H) throw new Error('The thermal frames file is incomplete');
        setPixels(new Uint8Array(buffer));
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [sessionKey, count, W, H]);

  useEffect(() => {
    clock.current = t;
  }, [t]);

  // playback advances the shared clock; it loops, as Hans's explorer does
  useEffect(() => {
    if (!playing) return undefined;
    let raf;
    let last = performance.now();
    const step = (now) => {
      clock.current = (clock.current + (now - last) / 1000) % duration;
      last = now;
      onTime(clock.current);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, duration, onTime]);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx || !frame) return;
    const img = ctx.createImageData(W, H);
    const { lut } = COLORMAPS[cmap];
    const span = displayMaxC - displayMinC;
    for (let i = 0; i < frame.length; i += 1) {
      const c = tempMinC + (frame[i] / 255) * (tempMaxC - tempMinC) + offset;
      const k = Math.max(0, Math.min(255, Math.round(((c - displayMinC) / span) * 255)));
      img.data[i * 4] = lut[k * 3];
      img.data[i * 4 + 1] = lut[k * 3 + 1];
      img.data[i * 4 + 2] = lut[k * 3 + 2];
      img.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }, [frame, cmap, W, H, tempMinC, tempMaxC, displayMinC, displayMaxC, offset]);

  /** Mean temperature inside each ROI box, read straight from this frame's pixels. */
  const roiTemps = useMemo(() => {
    if (!frame) return {};
    return Object.fromEntries(
      rois.map(({ key, box: [x, y, w, h] }) => {
        let sum = 0;
        for (let row = y; row < y + h; row += 1) {
          for (let col = x; col < x + w; col += 1) sum += frame[row * W + col];
        }
        return [key, toC(sum / (w * h))];
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, rois, W, offset]);

  const tone = (roi) => TONES[Math.max(0, tracks.findIndex((tr) => tr.key === roi.track)) % TONES.length];

  const point = (event) => {
    const r = event.currentTarget.getBoundingClientRect();
    const x = Math.floor(((event.clientX - r.left) / r.width) * W);
    const y = Math.floor(((event.clientY - r.top) / r.height) * H);
    setHover(x >= 0 && y >= 0 && x < W && y < H ? { x, y, px: event.clientX - r.left, py: event.clientY - r.top } : null);
  };

  if (error) return <p className={styles.error}>{error}</p>;

  return (
    <div className={styles.viewer}>
      <div className={styles.stage}>
        <div
          className={styles.image}
          style={{ aspectRatio: `${W} / ${H}` }}
          onPointerMove={point}
          onPointerLeave={() => setHover(null)}
        >
          <canvas ref={canvasRef} width={W} height={H} className={styles.canvas} role="img" aria-label={`Thermal frame ${index + 1} of ${count}`} />
          {!pixels && <div className={styles.loading}>Loading {count} thermal frames…</div>}
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={styles.overlay} aria-hidden="true">
            {rois.map((roi) => {
              const [x, y, w, h] = roi.box;
              return (
                <rect key={roi.key} x={x} y={y} width={w} height={h} fill="none" stroke={tone(roi)}
                  strokeWidth={2} strokeDasharray={roi.valid ? undefined : '4 3'} vectorEffect="non-scaling-stroke" />
              );
            })}
          </svg>
          {hover && frame && (
            <span className={styles.probe} style={{ left: hover.px + 12, top: hover.py + 12 }}>
              {toC(frame[hover.y * W + hover.x]).toFixed(2)} °C
            </span>
          )}
        </div>
        <div className={styles.scale}>
          <span>{displayMinC}°</span>
          <i style={{ background: gradientCss(cmap) }} aria-hidden="true" />
          <span>{displayMaxC}°C</span>
        </div>
      </div>

      <div className={styles.side}>
        <div className={styles.controls}>
          <button
            type="button"
            className={styles.play}
            onClick={() => setPlaying((p) => !p)}
            disabled={!pixels}
            aria-label={playing ? 'Pause' : 'Play'}
          >
            {playing ? <Pause size={15} /> : <Play size={15} />}
          </button>
          <span className={styles.clock}>
            {t.toFixed(1)} / {duration.toFixed(1)} s · frame {index + 1}/{count}
          </span>
        </div>

        <div className={styles.maps} role="group" aria-label="Colour map">
          {Object.entries(COLORMAPS).map(([key, m]) => (
            <button
              key={key}
              type="button"
              className={`${styles.map} ${cmap === key ? styles.mapOn : ''}`.trim()}
              aria-pressed={cmap === key}
              onClick={() => setCmap(key)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <ul className={styles.rois}>
          {rois.map((roi) => (
            <li key={roi.key}>
              <span className={styles.roiName}>
                <i style={{ background: tone(roi) }} aria-hidden="true" />
                {roi.label}
              </span>
              <span className={styles.roiTemp}>
                {roi.valid && roiTemps[roi.key] !== undefined ? `${roiTemps[roi.key].toFixed(1)} °C` : '—'}
              </span>
            </li>
          ))}
        </ul>

        {meta.simulated && <p className={styles.simulated}>Simulated thermal video — prototype data</p>}
        <p className="muted small">
          {W} × {H} px · {fps} frames/s · hover the image for any pixel's temperature. Play, or move across the
          graph below — both show the same moment.
        </p>
      </div>
    </div>
  );
}
