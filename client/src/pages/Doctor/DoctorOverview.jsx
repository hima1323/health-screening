import { useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import { Users, FileText, Siren, Activity, ChevronRight, CheckCircle2 } from 'lucide-react';
import { formatDate } from '../../components/SessionCard';
import { Card, StatusPill, Spinner } from '../../components/ui';
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import { matchesSearch, overviewStats } from './doctor';
import styles from './DoctorOverview.module.css';

/** The doctor's overview: four numbers, the latest readings against their ranges, who needs them, and what came in. */
export default function DoctorOverview() {
  const { patients, search } = useOutletContext();
  if (!patients) return <Spinner />;

  const shown = patients.filter((p) => matchesSearch(p, search));
  const stats = overviewStats(patients);

  return (
    <>
      <h1 className={styles.heading}>Overview</h1>

      <section className={styles.stats} aria-label="Summary">
        <StatCard
          label="Patients"
          icon={Users}
          value={stats.patients.total}
          segments={[
            { label: 'Needs attention', value: stats.patients.attention, tone: 'rose' },
            { label: 'Review', value: stats.patients.review, tone: 'amber' },
            { label: 'Stable', value: stats.patients.stable, tone: 'calm' },
          ]}
        />
        <StatCard
          label="Shared reports"
          icon={FileText}
          value={stats.reports.total}
          segments={[
            { label: 'Last 30 days', value: stats.reports.recent, tone: 'calm' },
            { label: 'Earlier', value: stats.reports.earlier, tone: 'faint' },
          ]}
        />
        <StatCard
          label="Need attention"
          icon={Siren}
          value={stats.attention.total}
          segments={[
            { label: 'Nurse check', value: stats.attention.nurseChecks, tone: 'rose' },
            { label: 'Out of range', value: stats.attention.other, tone: 'amber' },
          ]}
        />
        <StatCard
          label="Latest readings"
          icon={Activity}
          value={stats.readings.total}
          segments={[
            { label: 'Out of range', value: stats.readings.outOfRange, tone: 'rose' },
            { label: 'In range', value: stats.readings.inRange, tone: 'calm' },
          ]}
        />
      </section>

      <section className={styles.grid}>
        <Card className={styles.chartCard}>
          <ReadingsChart patients={shown} />
        </Card>
        <Card className={styles.queueCard}>
          <AttentionQueue patients={shown} />
        </Card>
        <Card className={styles.recentCard}>
          <RecentReports patients={shown} />
        </Card>
      </section>
    </>
  );
}

const TICKS = 36;

/** A headline number with a tick strip that splits it into its parts. */
function StatCard({ label, icon: Icon, value, segments }) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  // each tick takes the colour of the segment its midpoint falls in
  const ticks = Array.from({ length: TICKS }, (_, i) => {
    if (!total) return 'empty';
    let at = ((i + 0.5) / TICKS) * total;
    return segments.find((s) => (at -= s.value) < 0)?.tone ?? 'empty';
  });
  const first = segments[0];
  const last = segments[segments.length - 1];

  return (
    <Card className={styles.stat}>
      <div className={styles.statTop}>
        <p className={styles.statLabel}>{label}</p>
        <span className={styles.statIcon} aria-hidden="true">
          <Icon size={16} strokeWidth={1.7} />
        </span>
      </div>
      <p className={styles.statValue}>{value}</p>
      <div className={styles.statEnds}>
        <span>{first.label}</span>
        <span>{last.label}</span>
      </div>
      <div className={styles.ticks} role="img" aria-label={segments.map((s) => `${s.label} ${s.value}`).join(', ')}>
        {ticks.map((tone, i) => (
          <span key={i} className={`${styles.tick} ${styles[tone]}`} />
        ))}
      </div>
      <div className={styles.statEnds}>
        <strong>{first.value}</strong>
        <strong>{last.value}</strong>
      </div>
    </Card>
  );
}

/** Each patient's latest reading as a bar, over the shaded band of their normal range. */
function ReadingsChart({ patients }) {
  const [measure, setMeasure] = useState(RESULTS[0].key);
  const def = RESULTS.find((r) => r.key === measure);

  const bars = patients
    .map(({ patient, latest }) => {
      const r = latest[measure];
      if (!r) return null;
      return { id: patient._id, name: patient.name.split(' ')[0], code: latest.shareCode, value: r.value, range: rangePosition(r.value, r.normalRange) };
    })
    .filter(Boolean);

  // a shared scale padded around every value and range edge, so bands and bars compare fairly
  const edges = bars.flatMap((b) => [b.value, b.range?.low, b.range?.high]).filter((v) => v != null);
  const lo = Math.min(...edges);
  const hi = Math.max(...edges);
  const pad = (hi - lo) * 0.25 || 1;
  const min = lo - pad;
  const max = hi + pad;
  const pct = (v) => `${((v - min) / (max - min)) * 100}%`;

  return (
    <>
      <div className={styles.cardHead}>
        <div>
          <h3>Latest readings</h3>
          <p className="muted small">Each patient&rsquo;s most recent report · shaded band is their normal range</p>
        </div>
        <div className={styles.segmented} role="tablist" aria-label="Measure">
          {RESULTS.map((r) => (
            <button
              key={r.key}
              type="button"
              role="tab"
              aria-selected={r.key === measure}
              className={`${styles.segment} ${r.key === measure ? styles.segmentActive : ''}`.trim()}
              onClick={() => setMeasure(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {bars.length === 0 ? (
        <p className="muted">No readings to show.</p>
      ) : (
        <div className={styles.chart}>
          {bars.map((b) => {
            const out = b.range && b.range.position !== 'within';
            return (
              <Link key={b.id} to={`/doctor/reports/${b.code}`} className={styles.column} aria-label={`${b.name}: ${b.value} ${def.unit}`}>
                <div className={styles.plot}>
                  {b.range && <span className={styles.band} style={{ bottom: pct(b.range.low), top: `calc(100% - ${pct(b.range.high)})` }} />}
                  <span className={`${styles.bar} ${out ? styles.barOut : ''}`.trim()} style={{ height: pct(b.value) }}>
                    <span className={styles.barValue}>
                      {b.value}
                      <small> {def.unit}</small>
                    </span>
                  </span>
                </div>
                <span className={styles.barName}>{b.name}</span>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

/** Who to look at first: everyone whose latest report is not stable, most urgent first. */
function AttentionQueue({ patients }) {
  const queue = patients.filter((p) => p.latest.triage.level !== 'stable');
  return (
    <>
      <div className={styles.cardHead}>
        <h3>Needs your attention</h3>
      </div>
      {queue.length === 0 ? (
        <p className={`muted icon-line ${styles.allClear}`}>
          <CheckCircle2 size={15} aria-hidden="true" /> Every patient&rsquo;s latest report is stable.
        </p>
      ) : (
        <ul className={styles.queue}>
          {queue.map(({ patient, latest }) => (
            <li key={patient._id}>
              <Link to={`/doctor/reports/${latest.shareCode}`} className={styles.queueItem}>
                <span className={`${styles.level} ${styles[latest.triage.level]}`} aria-hidden="true" />
                <div className={styles.queueText}>
                  <p className={styles.queueName}>
                    {patient.name} <span>· {patient.age} y</span>
                  </p>
                  <p className="muted small">
                    {[
                      latest.nurseCheck?.queueId && 'Nurse check requested',
                      latest.triage.outOfRange.length > 0 &&
                        `${latest.triage.outOfRange.map((r) => r.label.toLowerCase()).join(' and ')} out of range`,
                    ]
                      .filter(Boolean)
                      .join(' · ') || 'Marked for review'}
                  </p>
                  <p className={styles.queueMeta}>
                    Session {latest.sessionId} · {formatDate(latest.recordedAt)}
                  </p>
                </div>
                <ChevronRight size={16} className={styles.chevron} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** The most recently shared reports across all patients. */
function RecentReports({ patients }) {
  const rows = patients
    .flatMap(({ patient, reports }) => reports.map((r) => ({ patient, r })))
    .sort((a, b) => new Date(b.r.sharedAt) - new Date(a.r.sharedAt))
    .slice(0, 8);

  return (
    <>
      <div className={styles.cardHead}>
        <h3>Recently shared</h3>
        <Link to="/doctor/patients" className={styles.more}>
          All patients <ChevronRight size={14} aria-hidden="true" />
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="muted">No reports yet. Use “Add shared report” when a patient gives you their code.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Patient</th>
                <th scope="col">Session</th>
                <th scope="col">Recorded</th>
                <th scope="col">Shared</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ patient, r }) => (
                <tr key={r.shareCode}>
                  <th scope="row">
                    <Link to={`/doctor/reports/${r.shareCode}`}>{patient.name}</Link>
                  </th>
                  <td>{r.sessionId}</td>
                  <td>{formatDate(r.recordedAt)}</td>
                  <td>{formatDate(r.sharedAt)}</td>
                  <td>
                    <StatusPill dot={false}>{r.triage.label}</StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
