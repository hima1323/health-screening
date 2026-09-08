import styles from './ErrorState.module.css';

export default function ErrorState({ message, hint }) {
  return (
    <div className={styles.state} role="alert">
      <p>{message}</p>
      {hint && <p className={styles.hint}>{hint}</p>}
    </div>
  );
}
