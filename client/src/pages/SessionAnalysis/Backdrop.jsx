import styles from './Backdrop.module.css';

/** The session page's background: a white page with three soft colour washes, drawn over the app's water scene. */
export default function Backdrop() {
  return (
    <div className={styles.backdrop} aria-hidden="true">
      <span className={`${styles.wash} ${styles.rose}`} />
      <span className={`${styles.wash} ${styles.calm}`} />
      <span className={`${styles.wash} ${styles.amber}`} />
    </div>
  );
}
