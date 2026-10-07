import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Stethoscope } from 'lucide-react';
import { getDoctorPatient } from '../../api';
import useResource from '../../hooks/useResource';
import { formatDate } from '../../components/SessionCard';
import { Spinner, ErrorState } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import Sparkline from './Sparkline';
import { initials, triage, triageReason } from './doctor';
import styles from './DoctorPatient.module.css';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** One patient: the nurse check if any, how each measure moved across shared reports, and one timeline of reports and screenings. */
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
      <Link to="/doctor/patients" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Patients
      </Link>

      <section className={`${styles.identity} ${styles[latest.triage.level]}`}>
        <span className={styles.avatar} aria-hidden="true">
          {initials(patient.name)}
        </span>
        <div className={styles.who}>
          <h1 className={styles.title}>{patient.name}</h1>
          <p className={styles.sub}>
            {patient.age} years · {reports.length} shared report{reports.length === 1 ? '' : 's'} · latest {formatDate(latest.recordedAt)}, session{' '}
            {latest.sessionId}
          </p>
        </div>
        <span className={styles.level}>{latest.triage.label}</span>
        <Link to={`/doctor/reports/${latest.shareCode}`} className={styles.primary}>
          Open latest report
        </Link>
      </section>

      {latest.nurseCheck?.queueId && (
        <section className={styles.nurse}>
          <span className={styles.nurseIcon} aria-hidden="true">
            <Stethoscope size={18} strokeWidth={1.8} />
          </span>
          <div>
            <p className={styles.nurseTitle}>Nurse check requested · queue {latest.nurseCheck.queueId}</p>
            <p className={styles.nurseBody}>
              {latest.nurseCheck.message}
              {latest.nurseCheck.room && ` Review ${latest.nurseCheck.reviewTime}, ${latest.nurseCheck.room.toLowerCase()}.`}
            </p>
          </div>
        </section>
      )}

      {/* each measure: where it stands now, how far it moved, and its line across reports */}
      <section className={styles.trends} aria-label="Readings over time">
        {RESULTS.map(({ key, label, unit }) => (
          <Trend key={key} label={label} unit={unit} reports={oldestFirst.filter((r) => r[key])} measure={key} />
        ))}
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle}>Timeline</h2>
          <p className={styles.panelNote}>Shared reports and screenings, newest first</p>
        </div>
        <Timeline reports={reports} history={history} />
      </section>
    </>
  );
}

function Trend({ label, unit, reports, measure }) {
  if (reports.length === 0) return null;
  const points = reports.map((r) => {
    const range = rangePosition(r[measure].value, r[measure].normalRange);
    return { value: r[measure].value, low: range?.low, high: range?.high };
  });
  const last = reports[reports.length - 1];
  const now = last[measure];
  const position = rangePosition(now.value, now.normalRange)?.position;
  const out = position && position !== 'within';
  const prev = reports.length > 1 ? reports[reports.length - 2] : null;
  const diff = prev && Math.round((now.value - prev[measure].value) * 10) / 10;
  const canDraw = points.every((p) => p.low != null);

  return (
    <article className={styles.trend}>
      <div className={styles.trendTop}>
        <h2 className={styles.trendLabel}>{label}</h2>
        <span className={`${styles.position} ${out ? styles.out : ''}`.trim()}>{POSITION_LABEL[position] ?? now.status}</span>
      </div>
      <p className={`${styles.value} ${out ? styles.out : ''}`.trim()}>
        {now.value}
        <small> {unit}</small>
      </p>
      <p className={styles.delta}>
        {prev ? `${diff > 0 ? '+' : ''}${diff} ${unit} since ${formatDate(prev.recordedAt)}` : 'First shared reading'} · normal {now.normalRange ?? '—'}
      </p>
      {canDraw && (
        <>
          <Sparkline points={points} label={`${label}: ${points.map((p) => p.value).join(', then ')} ${unit}`} />
          <div className={styles.axis} aria-hidden="true">
            <span>{formatDate(reports[0].recordedAt)}</span>
            {reports.length > 1 && <span>{formatDate(last.recordedAt)}</span>}
          </div>
        </>
      )}
    </article>
  );
}

/** Reports (filled dots) and screenings (rings), interleaved by date. */
function Timeline({ reports, history }) {
  const entries = [
    ...reports.map((r) => ({
      id: r.shareCode,
      at: new Date(r.recordedAt ?? r.sharedAt),
      kind: 'report',
      level: r.triage.level,
      title: `Shared report · ${r.sessionId}`,
      body: triageReason(r),
      code: r.shareCode,
    })),
    ...history.map((log) => ({
      id: log._id,
      at: new Date(log.occurredAt),
      kind: 'screening',
      level: /flag/i.test(log.status) ? 'attention' : /watch/i.test(log.status) ? 'review' : 'stable',
      title: `Screening · ${log.location}, ${log.status.toLowerCase()}`,
      body: [`Heart rate ${log.heartRate} bpm · temperature ${log.temp} °C`, log.clinicianDirective].filter(Boolean).join('. '),
    })),
  ].sort((a, b) => b.at - a.at);

  return (
    <ol className={styles.timeline}>
      {entries.map((e) => (
        <li key={e.id} className={`${styles.entry} ${styles[e.level]}`}>
          <span className={styles.when}>{formatDate(e.at)}</span>
          <span className={`${styles.mark} ${e.kind === 'screening' ? styles.ring : ''}`.trim()} aria-hidden="true" />
          <div className={styles.entryBody}>
            <div>
              <p className={styles.entryTitle}>{e.title}</p>
              <p className={styles.entryText}>{e.body}</p>
            </div>
            {e.code && (
              <Link to={`/doctor/reports/${e.code}`} className={styles.secondary}>
                View report
              </Link>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
