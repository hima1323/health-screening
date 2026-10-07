import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound } from 'lucide-react';
import { getDoctorReport } from '../../api';
import { normaliseCode } from './doctor';
import styles from './AddReportForm.module.css';

/**
 * A patient's code opens their report — and from then on it is in the doctor's list.
 * `tone="dark"` is the inline card on the overview; the sheet uses the light default.
 */
export default function AddReportForm({ onAdded, tone = 'light', autoFocus = false }) {
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function open(e) {
    e.preventDefault();
    const shareCode = normaliseCode(code);
    if (!shareCode) return;
    setBusy(true);
    setError(null);
    try {
      await getDoctorReport(shareCode);
      onAdded();
      navigate(`/doctor/reports/${shareCode}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form className={`${styles.form} ${styles[tone]}`} onSubmit={open}>
      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.hidden}>Share code</span>
          <input
            className={styles.input}
            placeholder="e.g. 894-DXK"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={16}
            autoFocus={autoFocus}
            aria-invalid={Boolean(error)}
          />
        </label>
        <button type="submit" className={styles.submit} disabled={busy || !code.trim()}>
          <KeyRound size={15} aria-hidden="true" /> {busy ? 'Opening…' : 'Open'}
        </button>
      </div>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
