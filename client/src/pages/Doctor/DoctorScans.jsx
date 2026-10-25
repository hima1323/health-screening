import { Link, useOutletContext } from 'react-router-dom';
import { Brain, ChevronRight, Inbox } from 'lucide-react';
import { formatDate } from '../../components/SessionCard';
import { Card, StatusPill, Spinner } from '../../components/ui';
import usePageTitle from '../../hooks/usePageTitle';
import { matchesSearch } from './doctor';
import styles from './DoctorScans.module.css';

const call = (summary) => (summary.abstain ? 'No clear reading' : `${summary.label === 'high' ? 'High' : 'Low'} mental load`);

/**
 * Every live scan the reasoning model read, across this doctor's patients, newest first. The demo station
 * replays recorded samples, so what the person was really doing is known and the model's call can be checked.
 */
export default function DoctorScans() {
  usePageTitle('Model results · Clinician');
  const { patients, search } = useOutletContext();
  if (!patients) return <Spinner />;

  const scans = patients
    .filter((p) => matchesSearch(p, search))
    .flatMap(({ patient, reports }) => reports.filter((r) => r.model).map((r) => ({ patient, report: r })))
    .sort((a, b) => new Date(b.report.recordedAt) - new Date(a.report.recordedAt));
  const decided = scans.filter(({ report }) => !report.model.summary.abstain);
  const right = decided.filter(({ report }) => report.model.summary.label === report.model.sample.truth).length;

  return (
    <>
      <div className={styles.head}>
        <h1 className={styles.title}>Model results</h1>
        <p className="muted small">
          {scans.length} live scan{scans.length === 1 ? '' : 's'} read by the reasoning model
          {decided.length > 0 && ` · its call matched what the person was doing in ${right} of ${decided.length}`}
        </p>
      </div>

      {scans.length === 0 ? (
        <Card>
          <p className="muted icon-line">
            <Inbox size={15} aria-hidden="true" />
            No model results yet. When a patient scans at a station and shares the report code, it appears here.
          </p>
        </Card>
      ) : (
        <ul className={styles.list}>
          {scans.map(({ patient, report }) => {
            const { summary, sample } = report.model;
            const matched = !summary.abstain && summary.label === sample.truth;
            return (
              <li key={report.sessionId}>
                <Link to={`/doctor/reports/${report.shareCode}`} className={styles.row}>
                  <span className={styles.icon} aria-hidden="true">
                    <Brain size={17} strokeWidth={1.7} />
                  </span>
                  <div className={styles.main}>
                    <p className={styles.name}>
                      {patient.name} · {formatDate(report.recordedAt)} · Session {report.sessionId}
                    </p>
                    <p className="muted small">
                      {Math.round(summary.confidence * 100)}% confidence · sample: {sample.task} (really {sample.truth}{' '}
                      load) · {matched ? 'call matches' : summary.abstain ? 'model abstained' : 'call does not match'}
                    </p>
                  </div>
                  <StatusPill dot={false}>{call(summary)}</StatusPill>
                  <ChevronRight size={16} aria-hidden="true" className={styles.chevron} />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
