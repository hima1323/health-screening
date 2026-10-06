import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronRight, Stethoscope } from 'lucide-react';
import { getDoctorPatient } from '../../api';
import useResource from '../../hooks/useResource';
import { formatDate } from '../../components/SessionCard';
import { Card, CardRow, StatusPill, Spinner, ErrorState } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { initials, triage } from './doctor';
import styles from './DoctorPatient.module.css';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** One patient: where they stand now, how their readings moved across shared reports, the reports, and their screenings. */
export default function DoctorPatient() {
  const { patientId } = useParams();
  const { data, error } = useResource(() => getDoctorPatient(patientId), [patientId]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { patient, history } = data;
  const when = (r) => new Date(r.recordedAt ?? r.sharedAt).getTime();
  const reports = data.reports.map((r) => ({ ...r, triage: triage(r) })).sort((a, b) => when(b) - when(a));
  const latest = reports[0];
  const oldestFirst = [...reports].reverse();

  return (
    <>
      <div className={styles.head}>
        <Link to="/doctor/patients" className={styles.back}>
          <ArrowLeft size={14} aria-hidden="true" /> Patients
        </Link>
        <div className={styles.identity}>
          <span className={styles.avatar} aria-hidden="true">
            {initials(patient.name)}
          </span>
          <div className={styles.who}>
            <h1 className={styles.title}>{patient.name}</h1>
            <p className="muted small">
              {patient.age} years · {reports.length} shared report{reports.length === 1 ? '' : 's'} · latest{' '}
              {formatDate(latest.recordedAt)}
            </p>
          </div>
          <StatusPill dot={false}>{latest.triage.label}</StatusPill>
        </div>
      </div>

      {latest.nurseCheck?.queueId && (
        <Card accent="rose" className={styles.nurse}>
          <p className={styles.nurseTitle}>
            <Stethoscope size={16} aria-hidden="true" /> Nurse check requested on {formatDate(latest.recordedAt)} · queue #
            {latest.nurseCheck.queueId}
          </p>
          <p className="muted small">{latest.nurseCheck.message}</p>
        </Card>
      )}

      {/* where they stand now: the latest value of each measure against its range */}
      <section className={styles.latest} aria-label="Latest readings">
        {RESULTS.filter(({ key }) => latest[key]).map(({ key, label, unit, icon: Icon }) => {
          const r = latest[key];
          const position = rangePosition(r.value, r.normalRange)?.position;
          return (
            <Card key={key} className={styles.tile}>
              <div className={styles.tileTop}>
                <span className={styles.tileLabel}>{label}</span>
                <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
              </div>
              <p className={`${styles.tileValue} ${position && position !== 'within' ? styles.out : ''}`.trim()}>
                {r.value}
                <small> {unit}</small>
              </p>
              <p className="muted small">
                Normal {r.normalRange ?? '—'} · <strong>{POSITION_LABEL[position] ?? r.status}</strong>
              </p>
            </Card>
          );
        })}
      </section>

      <div className={styles.columns}>
        <Card>
          <h3>Readings across shared reports</h3>
          <p className="muted small">Oldest to newest · out-of-range values in red</p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Measure</th>
                  {oldestFirst.map((r) => (
                    <th key={r.shareCode} scope="col">
                      {formatDate(r.recordedAt)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {RESULTS.map(({ key, label, unit }) => (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    {oldestFirst.map((r) => {
                      const v = r[key];
                      const position = v && rangePosition(v.value, v.normalRange)?.position;
                      return (
                        <td key={r.shareCode} className={position && position !== 'within' ? styles.out : ''}>
                          {v ? (
                            <>
                              {v.value} <small>{unit}</small>
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h3>Shared reports</h3>
          <ul className={styles.list}>
            {reports.map((r) => (
              <li key={r.shareCode}>
                <Link to={`/doctor/reports/${r.shareCode}`} className={styles.row}>
                  <div className={styles.rowMain}>
                    <p className={styles.rowTitle}>
                      {formatDate(r.recordedAt)} · Session {r.sessionId}
                    </p>
                    <p className="muted small">
                      {r.triage.outOfRange.length > 0
                        ? `Out of range: ${r.triage.outOfRange.map((x) => x.label.toLowerCase()).join(', ')}`
                        : 'All readings in range'}{' '}
                      · shared {formatDate(r.sharedAt)}
                    </p>
                  </div>
                  <StatusPill dot={false}>{r.triage.label}</StatusPill>
                  <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card>
        <h3>Screening history</h3>
        {history.length === 0 ? (
          <p className="muted small">No screenings recorded.</p>
        ) : (
          <ul className={styles.list}>
            {history.map((log) => (
              <li key={log._id} className={styles.historyItem}>
                <CardRow>
                  <div>
                    <p className={styles.rowTitle}>{log.dateLabel}</p>
                    <p className="muted small">
                      {log.type} · {log.location}
                    </p>
                  </div>
                  <StatusPill dot={false}>{log.status}</StatusPill>
                </CardRow>
                <p className={styles.vitals}>
                  Heart rate <strong>{log.heartRate} bpm</strong> · Temperature <strong>{log.temp} °C</strong>
                </p>
                {log.clinicianDirective && <p className="muted small">{log.clinicianDirective}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
