import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Leaf, ListChecks, Users, Search, CalendarDays, Plus, LogOut } from 'lucide-react';
import { getDoctorPatients } from '../../api';
import StillWaterScene from '../../components/StillWaterScene';
import { Sheet } from '../../components/InfoSheet';
import AddReportForm from './AddReportForm';
import { buildPatients, initials, levelCounts } from './doctor';
import styles from './DoctorShell.module.css';

/**
 * The doctor's desktop frame: a sidebar (add a report, where to go, who is signed in),
 * a top bar (search, today) and the page. The patient list loads once here and
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
  const counts = patients && levelCounts(patients);
  // the worklist badge counts who is waiting on the doctor; patients shows everyone
  const nav = [
    { to: '/doctor', label: 'Worklist', icon: ListChecks, end: true, badge: counts && counts.attention + counts.review, urgent: true },
    { to: '/doctor/patients', label: 'Patients', icon: Users, badge: counts?.all },
  ];
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

        <button type="button" className={styles.addButton} onClick={() => setAdding(true)} aria-haspopup="dialog">
          <Plus size={16} strokeWidth={2} aria-hidden="true" /> Add shared report
        </button>

        <nav className={styles.nav} aria-label="Doctor pages">
          {nav.map(({ to, label, icon: Icon, end, badge, urgent }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navActive : ''}`.trim()}>
              <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
              {label}
              {badge > 0 && <span className={`${styles.badge} ${urgent ? styles.badgeUrgent : ''}`.trim()}>{badge}</span>}
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
              placeholder="Search patients, sessions or codes"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search patients, sessions or codes"
            />
          </label>
          <span className={styles.date}>
            <CalendarDays size={15} aria-hidden="true" /> {today}
          </span>
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

/** The sidebar's add button opens this; the code form is the same one the worklist shows inline. */
function AddReport({ onClose, onAdded }) {
  const added = () => {
    onAdded();
    onClose();
  };
  return (
    <Sheet title="Add a shared report" onClose={onClose}>
      <p>Ask the patient for the code on their Aura Screen results.</p>
      <div className={styles.addForm}>
        <AddReportForm onAdded={added} autoFocus />
      </div>
    </Sheet>
  );
}
