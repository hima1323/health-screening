import styles from './HeroBanner.module.css';

/** The session page's opening banner: how many readings are fine, at a glance. */
export default function HeroBanner({ readings, minutes, sensors }) {
  const fine = readings.filter((r) => r.ok).length;

  return (
    <section className={styles.hero} aria-label="Your session in one look">
      <div className={styles.text}>
        <p className={styles.kicker}>Your session in one look</p>
        <p className={styles.big}>
          {fine}
          <span> of {readings.length}</span>
        </p>
        <p className={styles.sub}>readings are fine</p>
        <p className={styles.meta}>
          {minutes} min recorded · {sensors} sensors
        </p>
      </div>
    </section>
  );
}
