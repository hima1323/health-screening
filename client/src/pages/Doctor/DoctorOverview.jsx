import { useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import { ChevronRight, Inbox } from 'lucide-react';
import { formatDate } from '../../components/SessionCard';
import { Spinner } from '../../components/ui';
import { RESULTS } from '../../utils/results';
import AddReportForm from './AddReportForm';
import RangeTrack from './RangeTrack';
import { initials, levelCounts, matchesSearch, triageReason } from './doctor';
import styles from './DoctorOverview.module.css';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'attention', label: 'Needs attention' },
  { key: 'review', label: 'Review' },
  { key: 'stable', label: 'Stable' },
];

/** The doctor's worklist: who needs them most, each latest reading against its range, and what just came in. */
export default function DoctorOverview() {
  const { doctor, patients, search, reload } = useOutletContext();
  const [filter, setFilter] = useState('all');
  if (!patients) return <Spinner />;

  const counts = levelCounts(patients);
  const shown = patients.filter((p) => matchesSearch(p, search) && (filter === 'all' || p.latest.triage.level === filter));

  return (
    <>
      <section className={styles.intro}>
        <div>
          <h1 className={styles.heading}>
            {greeting()}, Dr. {doctor.name.replace(/^Dr\.?\s*/i, '').split(/\s+/).pop()}
          </h1>
          <p className={styles.summary}>{summary(counts, patients)}</p>
        </div>
        <div className={styles.filters} role="group" aria-label="Filter by triage">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              className={`${styles.filter} ${filter === key ? styles.filterOn : ''}`.trim()}
              onClick={() => setFilter(key)}
            >
              <span className={`${styles.filterDot} ${styles[key]}`} aria-hidden="true" />
              {label}
              <strong>{counts[key]}</strong>
            </button>
          ))}
        </div>
      </section>

      <section className={styles.grid}>
        <div className={`${styles.panel} ${styles.worklist}`}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>Worklist</h2>
            <p className={styles.panelNote}>Most urgent first · each track shows the latest reading against its normal band</p>
          </div>
          <Worklist patients={shown} empty={patients.length === 0 ? 'none' : 'filtered'} />
        </div>

        <div className={styles.side}>
          <section className={styles.addCard}>
            <h2 className={styles.panelTitle}>Add a shared report</h2>
            <p className={styles.addHint}>Ask the patient for the code on their Aura Screen results.</p>
            <AddReportForm onAdded={reload} tone="dark" />
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>Recently shared</h2>
              <Link to="/doctor/patients" className={styles.more}>
                All patients <ChevronRight size={14} aria-hidden="true" />
              </Link>
            </div>
            <RecentReports patients={patients.filter((p) => matchesSearch(p, search))} />
          </section>
        </div>
      </section>
    </>
  );
}

function greeting(hour = new Date().getHours()) {
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
}

/** "Two patients need you today. One has a nurse check waiting." */
function summary(counts, patients) {
  if (patients.length === 0) return 'No shared reports yet. Add one when a patient gives you their code.';
  const waiting = counts.attention + counts.review;
  const nurse = patients.filter((p) => p.latest.nurseCheck?.queueId).length;
  const first =
    waiting === 0
      ? 'Every patient’s latest report is stable.'
      : `${waiting} patient${waiting === 1 ? ' needs' : 's need'} you.`;
  return nurse ? `${first} ${nurse} ha${nurse === 1 ? 's a nurse check' : 've nurse checks'} waiting.` : first;
}

/** One row per patient: urgency, why, and each latest reading on its range track. */
function Worklist({ patients, empty }) {
  if (patients.length === 0) {
    return (
      <p className={`muted icon-line ${styles.empty}`}>
        <Inbox size={15} aria-hidden="true" />
        {empty === 'none' ? 'No patients yet. Add a shared report to start.' : 'No patients in this group.'}
      </p>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <div className={styles.table}>
        <div className={`${styles.row} ${styles.rowHead}`} aria-hidden="true">
          <span>Patient</span>
          <span>Why</span>
          {RESULTS.map((r) => (
            <span key={r.key}>{r.label}</span>
          ))}
          <span />
        </div>
        <ul className={styles.rows}>
          {patients.map(({ patient, latest }) => (
            <li key={patient._id}>
              <Link to={`/doctor/patients/${patient._id}`} className={`${styles.row} ${styles.item} ${styles[latest.triage.level]}`}>
                <span className={styles.who}>
                  <span className={styles.avatar} aria-hidden="true">
                    {initials(patient.name)}
                  </span>
                  <span className={styles.whoText}>
                    <span className={styles.name}>{patient.name}</span>
                    <span className={styles.meta}>
                      {patient.age} y · {latest.sessionId} · {formatDate(latest.recordedAt)}
                    </span>
                  </span>
                </span>
                <span className={styles.why}>
                  <span className={styles.level}>{latest.triage.label}</span>
                  <span className={styles.reason}>{triageReason(latest)}</span>
                </span>
                {RESULTS.map(({ key, label, unit }) => {
                  const r = latest[key];
                  const out = latest.triage.outOfRange.some((o) => o.key === key);
                  return (
                    <span key={key} className={styles.vital}>
                      {r ? (
                        <>
                          <span className={`${styles.vitalValue} ${out ? styles.out : ''}`.trim()}>
                            <span className={styles.vitalLabel}>{label} </span>
                            {r.value} <small>{unit}</small>
                          </span>
                          <RangeTrack value={r.value} normalRange={r.normalRange} unit={unit} />
                        </>
                      ) : (
                        <span className={styles.vitalValue}>—</span>
                      )}
                    </span>
                  );
                })}
                <ChevronRight size={18} className={styles.chevron} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** The most recently shared reports across all patients, as a short feed. */
function RecentReports({ patients }) {
  const rows = patients
    .flatMap(({ patient, reports }) => reports.map((r) => ({ patient, r })))
    .sort((a, b) => new Date(b.r.sharedAt) - new Date(a.r.sharedAt))
    .slice(0, 6);

  if (rows.length === 0) return <p className="muted small">Nothing shared yet.</p>;

  return (
    <ol className={styles.feed}>
      {rows.map(({ patient, r }) => (
        <li key={r.shareCode}>
          <span className={`${styles.feedDot} ${styles[r.triage.level]}`} aria-hidden="true" />
          <Link to={`/doctor/reports/${r.shareCode}`} className={styles.feedLink}>
            <span className={styles.feedName}>
              {patient.name} <span>· {r.sessionId}</span>
            </span>
            <span className={styles.feedSummary}>{triageReason(r)}</span>
            <span className={styles.feedWhen}>Shared {formatDate(r.sharedAt)}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
