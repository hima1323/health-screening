import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Clock } from 'lucide-react';
import { getDoctorReport } from '../../api';
import useResource from '../../hooks/useResource';
import { Spinner, ErrorState } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { formatDate } from '../../components/SessionCard';
import RangeTrack from './RangeTrack';
import { normaliseCode, triage } from './doctor';
import styles from './DoctorReport.module.css';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** One shared report, as the doctor reads it: the verdict first, every reading on its range, then the nurse check and history. */
export default function DoctorReport() {
  const code = normaliseCode(useParams().code);
  const { data, error } = useResource(() => getDoctorReport(code), [code]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { report, patient, history } = data;
  const level = triage(report);
  const readings = RESULTS.filter(({ key }) => report[key]);
  const recorded = report.recordedAt && new Date(report.recordedAt);

  return (
    <>
      <Link to={`/doctor/patients/${patient._id}`} className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> {patient.name}
      </Link>

      <section className={`${styles.verdict} ${styles[level.level]}`}>
        <div className={styles.verdictMain}>
          <p className={styles.eyebrow}>
            {level.label} · {level.outOfRange.length} of {readings.length} out of range
          </p>
          <h1 className={styles.headline}>{headline(level.outOfRange)}</h1>
          <p className={styles.verdictSub}>
            {patient.name}, {patient.age} · session {report.sessionId} · recorded {formatDate(recorded)}
            {recorded && `, ${recorded.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`}
          </p>
        </div>
        <dl className={styles.facts}>
          <div>
            <dt>Share code</dt>
            <dd className={styles.code}>{code}</dd>
          </div>
          <div>
            <dt>Shared</dt>
            <dd>{formatDate(report.sharedAt)}</dd>
          </div>
        </dl>
      </section>

      <div className={styles.columns}>
        <section className={styles.panel}>
          <h2 className={styles.panelTitle}>Readings</h2>
          <ul className={styles.readings}>
            {readings.map(({ key, label, unit }) => {
              const r = report[key];
              const position = rangePosition(r.value, r.normalRange)?.position;
              const out = position && position !== 'within';
              return (
                <li key={key} className={styles.reading}>
                  <div>
                    <h3 className={styles.readingLabel}>{label}</h3>
                    <p className={`${styles.value} ${out ? styles.out : ''}`.trim()}>
                      {r.value}
                      <small> {unit}</small>
                    </p>
                    <p className={`${styles.position} ${out ? styles.out : ''}`.trim()}>{POSITION_LABEL[position] ?? r.status}</p>
                  </div>
                  <div className={styles.readingDetail}>
                    <RangeTrack value={r.value} normalRange={r.normalRange} unit={unit} size="lg" />
                    <p className={styles.note}>
                      {r.note}
                      {r.normalRange && <span className={styles.range}> Normal {r.normalRange}.</span>}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <div className={styles.side}>
          {report.nurseCheck?.queueId && (
            <section className={styles.nurse}>
              <p className={styles.nurseTitle}>Nurse check · queue {report.nurseCheck.queueId}</p>
              <p className={styles.nurseBody}>{report.nurseCheck.message}</p>
              <p className={`${styles.nurseWhen} icon-line`}>
                <Clock size={13} aria-hidden="true" /> {report.nurseCheck.reviewTime} · {report.nurseCheck.room}
              </p>
            </section>
          )}

          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>Screening history</h2>
            {history.length === 0 ? (
              <p className="muted small">No screenings recorded.</p>
            ) : (
              <ol className={styles.history}>
                {history.map((log) => (
                  <li key={log._id}>
                    <p className={styles.historyHead}>
                      {log.dateLabel}
                      <span className={styles[statusLevel(log.status)]}>{log.status}</span>
                    </p>
                    <p className={styles.historyMeta}>
                      {log.location} · {log.heartRate} bpm · {log.temp} °C
                    </p>
                    {log.clinicianDirective && <p className={styles.historyMeta}>{log.clinicianDirective}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

/** "Heart rate and body temperature are above range." — said once, in words, before any number. */
function headline(outOfRange) {
  if (outOfRange.length === 0) return 'All key readings are within their normal ranges.';
  const names = outOfRange.map((r) => r.label.toLowerCase());
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
  const sentence = `${list[0].toUpperCase()}${list.slice(1)}`;
  return `${sentence} ${names.length === 1 ? 'is' : 'are'} out of range.`;
}

const statusLevel = (status) => (/flag/i.test(status) ? 'attention' : /watch/i.test(status) ? 'review' : 'stable');
