import { useEffect, useId, useState } from 'react';
import { ChevronRight, X } from 'lucide-react';
import styles from './InfoSheet.module.css';

/**
 * A tappable row that slides its content up from the bottom of the screen.
 * Phone screens use it for secondary detail that would otherwise force the
 * page to scroll. `position: fixed` is contained by the device frame, so the
 * sheet covers the phone screen, not the browser window.
 */
export default function InfoSheet({ icon: Icon, label, hint, title, children }) {
  const [open, setOpen] = useState(false);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      <button type="button" className={styles.trigger} onClick={() => setOpen(true)} aria-haspopup="dialog">
        {Icon && (
          <span className={styles.triggerIcon} aria-hidden="true">
            <Icon size={16} strokeWidth={1.7} />
          </span>
        )}
        <span className={styles.triggerText}>
          <span className={styles.triggerLabel}>{label}</span>
          {hint && <span className={styles.triggerHint}>{hint}</span>}
        </span>
        <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
      </button>

      {open && (
        <div className={styles.backdrop} onClick={() => setOpen(false)}>
          <div
            className={styles.sheet}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            onClick={(e) => e.stopPropagation()}
          >
            <span className={styles.grabber} aria-hidden="true" />
            <div className={styles.head}>
              <h3 id={titleId} className={styles.title}>
                {title ?? label}
              </h3>
              <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close">
                <X size={16} />
              </button>
            </div>
            <div className={styles.body}>{children}</div>
          </div>
        </div>
      )}
    </>
  );
}
