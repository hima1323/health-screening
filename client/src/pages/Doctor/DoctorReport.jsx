import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Stethoscope, Clock } from 'lucide-react';
import { getDoctorReport } from '../../api';
import useResource from '../../hooks/useResource';
import { Card, CardRow, CardHeading, IconBadge, StatusPill, Spinner, ErrorState } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { formatDate } from '../../components/SessionCard';
import { normaliseCode, triage } from './doctor';
import styles from './Doctor.module.css';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** One shared report, as the doctor reads it: who, how urgent, every reading against its range, and the history. */
export default function DoctorReport() {
  const code = normaliseCode(useParams().code);
  const { data, error } = useResource(() => getDoctorReport(code), [code]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { report, patient, history } = data;
  const level = triage(report);

  return (
    <>
      <div className={styles.pageHead}>
        <Link to={`/doctor/patients/${patient._id}`} className={styles.back}>
          <ArrowLeft size={14} aria-hidden="true" /> {patient.name}
        </Link>
        <h1 className={styles.pageTitle}>{patient.name}</h1>
        <p className="muted small">Shared report · code {code}</p>
      </div>

      <Card accent={level.level === 'attention' ? 'rose' : level.level === 'review' ? 'amber' : 'calm'}>
        <CardRow>
          <div>
            <h3>
              {patient.name}, {patient.age}
            </h3>
            <p className="muted small">
              Session {report.sessionId} · recorded {formatDate(report.recordedAt)} · shared {formatDate(report.sharedAt)}
            </p>
          </div>
          <StatusPill dot={false}>{level.label}</StatusPill>
        </CardRow>
        <p className={styles.verdict}>
          {level.outOfRange.length === 0
            ? 'All key readings are within their normal ranges.'
            : `${level.outOfRange.length} of ${RESULTS.length} key readings are out of range: ${level.outOfRange
                .map((r) => r.label.toLowerCase())
                .join(' and ')}.`}
        </p>

        {report.nurseCheck?.queueId && (
          <div className={styles.nurse}>
            <CardHeading>
              <IconBadge tone="rose">
                <Stethoscope size={16} strokeWidth={1.7} />
              </IconBadge>
              <strong>Nurse check requested · queue #{report.nurseCheck.queueId}</strong>
            </CardHeading>
            <p className="muted small">{report.nurseCheck.message}</p>
            <p className="muted small icon-line">
              <Clock size={12} aria-hidden="true" /> {report.nurseCheck.reviewTime} · {report.nurseCheck.room}
            </p>
          </div>
        )}
      </Card>

      <Card>
        <h3>Readings</h3>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Reading</th>
                <th scope="col">Normal</th>
                <th scope="col">Position</th>
              </tr>
            </thead>
            <tbody>
              {RESULTS.filter(({ key }) => report[key]).map(({ key, label, unit }) => {
                const r = report[key];
                const position = rangePosition(r.value, r.normalRange)?.position;
                return (
                  <tr key={key}>
                    <th scope="row">
                      {label}
                      {r.note && <span className={styles.note}>{r.note}</span>}
                    </th>
                    <td className={styles.reading}>
                      {r.value} <span className={styles.unit}>{unit}</span>
                    </td>
                    <td>{r.normalRange ?? '—'}</td>
                    <td>
                      <span className={`${styles.position} ${position ? styles[position] : ''}`.trim()}>
                        {POSITION_LABEL[position] ?? r.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <h3>Screening history</h3>
        {history.length === 0 ? (
          <p className="muted small">No earlier screenings.</p>
        ) : (
          <ul className={styles.history}>
            {history.map((log) => (
              <li key={log._id} className={styles.historyItem}>
                <CardRow>
                  <div>
                    <p className={styles.rowName}>{log.dateLabel}</p>
                    <p className="muted small">
                      {log.type} · {log.location}
                    </p>
                  </div>
                  <StatusPill dot={false}>{log.status}</StatusPill>
                </CardRow>
                <p className={styles.historyVitals}>
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
