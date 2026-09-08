import styles from './IconBadge.module.css';

/** A round glass chip holding a single icon. */
export default function IconBadge({ tone, className = '', children }) {
  return (
    <span className={`${styles.badge} ${tone ? styles[tone] : ''} ${className}`.trim()} aria-hidden="true">
      {children}
    </span>
  );
}
