import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { getStudySession } from '../../api';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import ReadingsSummary from '../../components/ReadingsSummary';
import { formatDate, sessionId } from '../../components/SessionCard';
import { Card, Spinner, ErrorState } from '../../components/ui';
import styles from './SessionAnalysis.module.css';

// TEMPORARY (not committed): version A of the session page, served on port 5174 for A/B screenshots
export default function VersionA() {
  const { key } = useParams();
  const { data, error } = useResource(() => getStudySession(key), [key]);
  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;
  const s = data.session;
  return (
    <Layout eyebrow={`Session ${sessionId(s.sessionKey)} · ${formatDate(s.recordedOn)}`} title={s.label}>
      <Link to="/timeline" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Past sessions
      </Link>
      {s.summary?.readings?.length > 0 && (
        <Card>
          <ReadingsSummary summary={s.summary} advice={s.assessment?.advice} />
        </Card>
      )}
      <p className="muted small">Your doctor sees the full analysis. A screening aid, not a diagnosis.</p>
      <p className={`muted small ${styles.source}`}>
        {s.source.note}{' '}
        <a href={s.source.url} target="_blank" rel="noreferrer">
          Source <ExternalLink size={11} aria-hidden="true" />
        </a>
      </p>
    </Layout>
  );
}
