import styles from './Card.module.css';

const EDGE_BY_ACCENT = {
  rose: styles.edgeRose,
  amber: styles.edgeAmber,
  sage: styles.edgeSage,
};

/** A tinted glass surface, optionally with a coloured status stripe. */
export default function Card({ accent, className = '', children, ...rest }) {
  return (
    <section className={`${styles.card} ${className}`.trim()} {...rest}>
      {accent && <span className={`${styles.edge} ${EDGE_BY_ACCENT[accent]}`} aria-hidden="true" />}
      {children}
    </section>
  );
}

/** A title on the left, a pill or badge on the right. */
export function CardRow({ className = '', children }) {
  return <div className={`${styles.row} ${className}`.trim()}>{children}</div>;
}

/** An icon badge sitting beside a heading. */
export function CardHeading({ className = '', children }) {
  return <div className={`${styles.heading} ${className}`.trim()}>{children}</div>;
}
