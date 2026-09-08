import { useRef, useState } from 'react';
import styles from './AuraOrb.module.css';

const BANDS = [
  { top: '43%', opacity: 1, delay: '0s' },
  { top: '50%', opacity: 0.55, delay: '1.2s' },
  { top: '57%', opacity: 0.35, delay: '2.4s' },
];

const RING_RADIUS = 106;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/**
 * The glass sphere that carries a reading.
 *
 * Interactive: it tilts toward the pointer while the highlight, refraction bands
 * and interior horizon parallax against it, and a click sends a ripple outward.
 *
 * @param {number} size      widest the orb may render, in px
 * @param {object} [ring]    { progress: 0..1, inset: px } to wrap it in a capture ring
 */
export default function AuraOrb({ size = 184, value, caption, children, ring }) {
  const stageRef = useRef(null);
  const [pulses, setPulses] = useState([]);

  const setTilt = (mx, my) => {
    stageRef.current?.style.setProperty('--mx', mx);
    stageRef.current?.style.setProperty('--my', my);
  };

  const handlePointerMove = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    setTilt(
      ((event.clientX - bounds.left) / bounds.width - 0.5).toFixed(3),
      ((event.clientY - bounds.top) / bounds.height - 0.5).toFixed(3)
    );
  };

  const handlePointerLeave = () => setTilt(0, 0);

  const addPulse = () => setPulses((current) => [...current, Date.now() + Math.random()]);

  const removePulse = (id) => setPulses((current) => current.filter((pulse) => pulse !== id));

  const orb = (
    <div
      className={styles.orb}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
      onPointerDown={addPulse}
    >
      <span className={styles.horizon} aria-hidden="true" />
      {BANDS.map((band) => (
        <span
          key={band.top}
          className={styles.band}
          style={{ top: band.top, opacity: band.opacity, animationDelay: band.delay }}
          aria-hidden="true"
        />
      ))}
      <span className={styles.ripples} aria-hidden="true" />
      <span className={styles.specular} aria-hidden="true" />

      {pulses.map((id) => (
        <span
          key={id}
          className={styles.pulse}
          onAnimationEnd={() => removePulse(id)}
          aria-hidden="true"
        />
      ))}

      <div className={styles.content}>
        <div className={`numeral ${String(value).length > 3 ? styles.valueLong : styles.value}`}>{value}</div>
        {caption && <div className={styles.caption}>{caption}</div>}
        {children}
      </div>
    </div>
  );

  return (
    <div
      className={styles.stage}
      ref={stageRef}
      style={{ '--orb-max': `${size}px`, '--ring-inset': `${ring?.inset ?? 22}px` }}
    >
      {ring ? (
        <div className={styles.ring}>
          <svg viewBox="0 0 240 240" className={styles.ringSvg} aria-hidden="true">
            <defs>
              <linearGradient id="auraOrbRing" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#E4A79C" />
                <stop offset="55%" stopColor="#D9C3CB" />
                <stop offset="100%" stopColor="#8FB3C7" />
              </linearGradient>
            </defs>
            <circle cx="120" cy="120" r="114" className={styles.ringTrackDotted} />
            <circle cx="120" cy="120" r={RING_RADIUS} className={styles.ringTrack} />
            <circle
              cx="120"
              cy="120"
              r={RING_RADIUS}
              className={styles.ringArc}
              strokeDasharray={RING_CIRCUMFERENCE}
              strokeDashoffset={RING_CIRCUMFERENCE * (1 - ring.progress)}
            />
          </svg>
          {orb}
        </div>
      ) : (
        orb
      )}
      <span className={styles.shadow} aria-hidden="true" />
      <span className={styles.reflection} aria-hidden="true" />
    </div>
  );
}
