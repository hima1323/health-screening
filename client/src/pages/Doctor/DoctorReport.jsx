import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Clock, ShieldCheck, Sun, ScanFace, Move, Radio, Activity } from 'lucide-react';
import { getDoctorReport } from '../../api';
import useResource from '../../hooks/useResource';
import { Spinner, ErrorState, StatusPill } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { formatDate } from '../../components/SessionCard';
import RangeTrack from './RangeTrack';
import { normaliseCode, triage } from './doctor';
import styles from './DoctorReport.module.css';

const POSITION_LABEL = { above: 'Above range', below: 'Below range', within: 'In range' };

/** Readings some measures carry beyond the headline value. */
const EXTRAS = {
  heartRate: [
    { key: 'resting', label: 'Resting', unit: 'bpm' },
    { key: 'peak', label: 'Peak', unit: 'bpm' },
    { key: 'variability', label: 'Variability' },
  ],
};

/** The capture conditions the station recorded, in the order a clinician checks them. */
const ENVIRONMENT = [
  { key: 'lighting', label: 'Lighting', icon: Sun },
  { key: 'position', label: 'Position', icon: ScanFace },
  { key: 'motion', label: 'Motion', icon: Move },
  { key: 'sensorStream', label: 'Sensor signal', icon: Radio },
];

/** One shared report, as the doctor reads it: the verdict first, every reading on its range, then the nurse check and history. */
export default function DoctorReport() {
  const code = normaliseCode(useParams().code);
  const { data, error } = useResource(() => getDoctorReport(code), [code]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { report, patient, history, scan } = data;
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
            {readings.map(({ key, label, unit, icon: Icon, measures }) => {
              const r = report[key];
              const position = rangePosition(r.value, r.normalRange)?.position;
              const out = position && position !== 'within';
              const extras = (EXTRAS[key] ?? []).filter((x) => r[x.key] != null && r[x.key] !== '');
              return (
                <li key={key} className={styles.reading}>
                  <div>
                    <h3 className={styles.readingLabel}>
                      <Icon size={15} strokeWidth={1.8} aria-hidden="true" /> {label}
                    </h3>
                    <p className={`${styles.value} ${out ? styles.out : ''}`.trim()}>
                      {r.value}
                      <small> {unit}</small>
                    </p>
                    <p className={`${styles.position} ${out ? styles.out : ''}`.trim()}>{POSITION_LABEL[position] ?? r.status}</p>
                  </div>
                  <div className={styles.readingDetail}>
                    <div className={styles.readingTop}>
                      {r.status && <StatusPill>{r.status}</StatusPill>}
                      {r.normalRange && <span className={styles.range}>Normal {r.normalRange}</span>}
                    </div>
                    <RangeTrack value={r.value} normalRange={r.normalRange} unit={unit} size="lg" />
                    {extras.length > 0 && (
                      <dl className={styles.extras}>
                        {extras.map((x) => (
                          <div key={x.key}>
                            <dt>{x.label}</dt>
                            <dd>
                              {r[x.key]}
                              {x.unit && <small> {x.unit}</small>}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {r.note && <p className={styles.note}>{r.note}</p>}
                    <p className={styles.measures}>{measures}</p>
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

          {scan && <ScanPanel scan={scan} />}

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

      {report.encryptionNote && (
        <p className={`${styles.secure} icon-line`}>
          <ShieldCheck size={13} aria-hidden="true" /> {report.encryptionNote}
        </p>
      )}
    </>
  );
}

const capitalise = (text) => text.charAt(0).toUpperCase() + text.slice(1);

/** Where and how the readings were captured: station, steps run, capture conditions, and the ECG fallback. */
function ScanPanel({ scan }) {
  const conditions = ENVIRONMENT.filter(({ key }) => scan.environment?.[key]);
  return (
    <section className={styles.panel}>
      <div className={styles.scanHead}>
        <h2 className={styles.panelTitle}>Scan session</h2>
        {scan.status && <StatusPill>{scan.status}</StatusPill>}
      </div>
      <p className={styles.historyMeta}>
        {capitalise(scan.stationId.replace(/-/g, ' '))}
        {scan.steps?.length > 0 && ` · ${scan.steps.join(' → ')}`}
      </p>
      {conditions.length > 0 && (
        <dl className={styles.conditions}>
          {conditions.map(({ key, label, icon: Icon }) => (
            <div key={key}>
              <dt>
                <Icon size={13} strokeWidth={1.8} aria-hidden="true" /> {label}
              </dt>
              <dd>{scan.environment[key]}</dd>
            </div>
          ))}
        </dl>
      )}
      {scan.ecgFallback?.title && (
        <div className={styles.ecg}>
          <p className={styles.ecgTitle}>
            <Activity size={14} strokeWidth={1.8} aria-hidden="true" /> {scan.ecgFallback.title}
            {scan.ecgFallback.badge && <span>{scan.ecgFallback.badge}</span>}
          </p>
          {scan.ecgFallback.description && <p className={styles.historyMeta}>{capitalise(scan.ecgFallback.description)}</p>}
        </div>
      )}
    </section>
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
