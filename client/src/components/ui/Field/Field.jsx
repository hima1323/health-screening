import styles from './Field.module.css';

/**
 * A labelled form control on the glass surface.
 * `as` picks the element: 'input' (default), 'select' or 'textarea'.
 * `trailing` sits inside the control — a password reveal button, say.
 */
export default function Field({
  label,
  hint,
  trailing,
  as: Element = 'input',
  className = '',
  children,
  ...rest
}) {
  return (
    <label className={`${styles.field} ${className}`.trim()}>
      <span className={styles.caption}>
        {label}
        {rest.required && <em className={styles.required}> required</em>}
      </span>
      <span className={styles.controlWrap}>
        <Element className={`${styles.control} ${trailing ? styles.hasTrailing : ''}`.trim()} {...rest}>
          {children}
        </Element>
        {trailing && <span className={styles.trailing}>{trailing}</span>}
      </span>
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
}

/** Two or three fields sharing a row, stacking on narrow screens. */
export function FieldRow({ className = '', children }) {
  return <div className={`${styles.row} ${className}`.trim()}>{children}</div>;
}
