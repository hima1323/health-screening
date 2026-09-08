import styles from './Button.module.css';

/** `primary` is the dark ink pill; `link` is the quiet text action. */
export default function Button({ variant = 'primary', className = '', children, ...rest }) {
  return (
    <button type="button" className={`${styles[variant]} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}
