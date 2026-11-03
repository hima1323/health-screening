import { Link, useOutletContext } from 'react-router-dom';
import { Brain, ChevronRight, Inbox } from 'lucide-react';
import { formatDate } from '../../components/SessionCard';
import { Card, StatusPill, Spinner } from '../../components/ui';
import usePageTitle from '../../hooks/usePageTitle';
import { modelCall } from '../../utils/reasoning';
import { matchesSearch } from './doctor';
import styles from './DoctorScans.module.css';

/** What the scan was and whether the call can be checked, for either model. */
function detail(report) {
  if (report.reasoning) {
    const { rule, sample } = report.reasoning;
    const ref = sample.reference_level;
    const check = ref ? (ref === report.reasoning.level ? ' · matches the reference' : ' · differs from the reference') : '';
    return `Rule ${rule.id}: ${rule.reason}${check}`;
  }
  const { summary, sample } = report.model;
  const matched = !summary.abstain && summary.label === sample.truth;
  return `${Math.round(summary.confidence * 100)}% confidence · ${sample.task} · ${
    matched ? 'call matches' : summary.abstain ? 'model abstained' : 'call does not match'
  }`;
}

/** Whether the call could be checked against a known answer, and if it was right. */
function checked(report) {
  if (report.reasoning) {
    const ref = report.reasoning.sample.reference_level;
    return ref ? { right: ref === report.reasoning.level } : null;
  }
  const { summary, sample } = report.model;
  return summary.abstain ? null : { right: summary.label === sample.truth };
}

/**
 * Every live scan the reasoning model read, across this doctor's patients, newest first. Where the demo case
 * carries a reference answer, the model's call is checked against it.
 */
export default function DoctorScans() {
  usePageTitle('Model results · Clinician');
  const { patients, search } = useOutletContext();
  if (!patients) return <Spinner />;

  const scans = patients
    .filter((p) => matchesSearch(p, search))
    .flatMap(({ patient, reports }) => reports.filter((r) => modelCall(r)).map((r) => ({ patient, report: r })))
    .sort((a, b) => new Date(b.report.recordedAt) - new Date(a.report.recordedAt));
  const decided = scans.map(({ report }) => checked(report)).filter(Boolean);
  const right = decided.filter((c) => c.right).length;

  return (
    <>
      <div className={styles.head}>
        <h1 className={styles.title}>Model results</h1>
        <p className="muted small">
          {scans.length} live scan{scans.length === 1 ? '' : 's'} read by the reasoning model
          {decided.length > 0 && ` · its call matched the known answer in ${right} of ${decided.length}`}
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
          {scans.map(({ patient, report }) => (
            <li key={report.sessionId}>
              <Link to={`/doctor/reports/${report.shareCode}`} className={styles.row}>
                <span className={styles.icon} aria-hidden="true">
                  <Brain size={17} strokeWidth={1.7} />
                </span>
                <div className={styles.main}>
                  <p className={styles.name}>
                    {patient.name} · {formatDate(report.recordedAt)} · Session {report.sessionId}
                  </p>
                  <p className="muted small">{detail(report)}</p>
                </div>
                <StatusPill dot={false}>{modelCall(report).title}</StatusPill>
                <ChevronRight size={16} aria-hidden="true" className={styles.chevron} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
