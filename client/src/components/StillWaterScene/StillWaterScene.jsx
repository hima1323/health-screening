import styles from './StillWaterScene.module.css';

const RIPPLES = [
  { top: '18%', opacity: 1 },
  { top: '34%', opacity: 0.6 },
  { top: '52%', opacity: 0.45 },
  { top: '70%', opacity: 0.35 },
];

/** The fixed backdrop: rose sky above, still water below. */
export default function StillWaterScene() {
  return (
    <div className={styles.scene} aria-hidden="true">
      <div className={styles.sky} />
      <div className={`${styles.cloud} ${styles.cloud1}`} />
      <div className={`${styles.cloud} ${styles.cloud2}`} />
      <div className={`${styles.cloud} ${styles.cloud3}`} />
      <div className={styles.roseBand} />
      <div className={styles.water}>
        {RIPPLES.map((ripple) => (
          <div key={ripple.top} className={styles.ripple} style={{ top: ripple.top, opacity: ripple.opacity }} />
        ))}
      </div>
      <div className={styles.scrim} />
    </div>
  );
}
