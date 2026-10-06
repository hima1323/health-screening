import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Leaf, LayoutDashboard, Users, Search, CalendarDays, FilePlus2, LogOut, KeyRound } from 'lucide-react';
import { getDoctorPatients, getDoctorReport } from '../../api';
import StillWaterScene from '../../components/StillWaterScene';
import { Sheet } from '../../components/InfoSheet';
import { Button, Field } from '../../components/ui';
import { buildPatients, initials, normaliseCode } from './doctor';
import styles from './DoctorShell.module.css';

const NAV = [
  { to: '/doctor', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/doctor/patients', label: 'Patients', icon: Users },
];

/**
 * The doctor's desktop frame: a sidebar (where to go, who is signed in), a top bar
 * (search, today, add a report) and the page. The patient list loads once here and
 * reaches every page through the outlet context, with `reload` after a new code is added.
 */
export default function DoctorShell({ doctor, signOut }) {
  const [raw, setRaw] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(false);

  const reload = useCallback(() => {
    getDoctorPatients().then(
      ({ patients }) => setRaw(patients),
      (err) => setError(err.message)
    );
  }, []);
  useEffect(reload, [reload]);

  const patients = raw && buildPatients(raw);
  const today = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());

  return (
    <div className={styles.shell}>
      <StillWaterScene />

      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            <Leaf size={18} strokeWidth={1.6} />
          </span>
          <div>
            <p className={styles.brandName}>Aura Screen</p>
            <p className={styles.brandSub}>Clinician</p>
          </div>
        </div>

        <nav className={styles.nav} aria-label="Doctor pages">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navActive : ''}`.trim()}>
              <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className={styles.profile}>
          {doctor.avatarUrl ? (
            <img className={styles.avatar} src={doctor.avatarUrl} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className={styles.avatar} aria-hidden="true">
              {initials(doctor.name)}
            </span>
          )}
          <div className={styles.profileText}>
            <p className={styles.profileName}>{doctor.name}</p>
            <p className={styles.profileSub}>{doctor.specialty || doctor.email}</p>
          </div>
          <button type="button" className={styles.signOut} onClick={signOut} aria-label="Sign out">
            <LogOut size={15} aria-hidden="true" />
          </button>
        </div>
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <label className={styles.search}>
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              placeholder="Search patients or sessions"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search patients or sessions"
            />
          </label>
          <span className={styles.date}>
            <CalendarDays size={15} aria-hidden="true" /> {today}
          </span>
          <Button className={styles.addButton} onClick={() => setAdding(true)} aria-haspopup="dialog">
            <FilePlus2 size={15} aria-hidden="true" /> Add shared report
          </Button>
        </header>

        <main className={styles.page}>
          {error ? (
            <p className={styles.loadError} role="alert">
              {error}
            </p>
          ) : (
            <Outlet context={{ doctor, patients, search, reload }} />
          )}
        </main>
      </div>

      {adding && <AddReport onClose={() => setAdding(false)} onAdded={reload} />}
    </div>
  );
}

/** A patient's code opens their report — and from then on it is in the doctor's list. */
function AddReport({ onClose, onAdded }) {
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
      onClose();
      navigate(`/doctor/reports/${shareCode}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Sheet title="Add a shared report" onClose={onClose}>
      <p>Ask the patient for the code on their Aura Screen results.</p>
      <form className={styles.addForm} onSubmit={open}>
        <Field
          label="Share code"
          placeholder="e.g. 894-DXK"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={16}
          autoFocus
          aria-invalid={Boolean(error)}
        />
        {error && (
          <p className={styles.formError} role="alert">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy || !code.trim()}>
          <KeyRound size={15} aria-hidden="true" /> {busy ? 'Opening…' : 'Open report'}
        </Button>
      </form>
    </Sheet>
  );
}
