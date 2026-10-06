import { Link, useOutletContext } from 'react-router-dom';
import { ChevronRight, Inbox } from 'lucide-react';
import { formatDate } from '../../components/SessionCard';
import { Card, StatusPill, Spinner } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { initials, matchesSearch } from './doctor';
import styles from './DoctorPatients.module.css';

/** Every patient who shared a report with this doctor, as cards, most urgent first. A card opens the patient. */
export default function DoctorPatients() {
  const { patients, search } = useOutletContext();
  if (!patients) return <Spinner />;

  const shown = patients.filter((p) => matchesSearch(p, search));

  return (
    <>
      <div className={styles.head}>
        <h1 className={styles.title}>Patients</h1>
        <p className="muted small">
          {search.trim()
            ? `${shown.length} of ${patients.length} match “${search.trim()}”`
            : `${patients.length} patient${patients.length === 1 ? ' has' : 's have'} shared reports with you`}
        </p>
      </div>

      {shown.length === 0 ? (
        <Card>
          <p className="muted icon-line">
            <Inbox size={15} aria-hidden="true" />
            {patients.length === 0
              ? 'No patients yet. Use “Add shared report” when a patient gives you their code.'
              : 'No patient matches that search.'}
          </p>
        </Card>
      ) : (
        <ul className={styles.grid}>
          {shown.map((entry) => (
            <li key={entry.patient._id}>
              <PatientCard entry={entry} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function PatientCard({ entry: { patient, reports, latest } }) {
  return (
    <Link to={`/doctor/patients/${patient._id}`} className={`${styles.card} ${styles[latest.triage.level]}`}>
      <div className={styles.cardTop}>
        <span className={styles.avatar} aria-hidden="true">
          {initials(patient.name)}
        </span>
        <div className={styles.who}>
          <p className={styles.name}>{patient.name}</p>
          <p className="muted small">{patient.age} years</p>
        </div>
        <StatusPill dot={false}>{latest.triage.label}</StatusPill>
      </div>

      {/* the latest reading of each measure, coloured by where it falls */}
      <dl className={styles.readings}>
        {RESULTS.filter(({ key }) => latest[key]).map(({ key, label, unit }) => {
          const r = latest[key];
          const position = rangePosition(r.value, r.normalRange)?.position;
          return (
            <div key={key} className={styles.reading}>
              <dt>{label}</dt>
              <dd className={position && position !== 'within' ? styles.out : ''}>
                {r.value}
                <small> {unit}</small>
              </dd>
            </div>
          );
        })}
      </dl>

      <p className={styles.reason}>
        {[
          latest.nurseCheck?.queueId && 'Nurse check requested',
          latest.triage.outOfRange.length > 0 &&
            `${latest.triage.outOfRange.map((r) => r.label.toLowerCase()).join(' and ')} out of range`,
        ]
          .filter(Boolean)
          .join(' · ') || 'All latest readings in range'}
      </p>

      <div className={styles.cardFoot}>
        <span>
          {reports.length} shared report{reports.length === 1 ? '' : 's'} · latest {formatDate(latest.recordedAt)}
        </span>
        <ChevronRight size={16} aria-hidden="true" />
      </div>
    </Link>
  );
}
