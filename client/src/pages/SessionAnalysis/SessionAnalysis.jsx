import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { getStudySession } from '../../api';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import SyncedTracks from '../../components/SyncedTracks';
import PhaseTable from '../../components/PhaseTable';
import FusionPanel from '../../components/FusionPanel';
import PipelineTrace from '../../components/PipelineTrace';
import AssessmentPanel from '../../components/AssessmentPanel';
import { Card, CardRow, StatusPill, Spinner, ErrorState } from '../../components/ui';
import styles from './SessionAnalysis.module.css';

/**
 * One past session, analysed across its modalities: the signals on a shared
 * clock, every metric by phase, what the channels conclude together, and the
 * preprocessing that produced it all.
 */
export default function SessionAnalysis() {
  const { key } = useParams();
  const { data, error } = useResource(() => getStudySession(key), [key]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const s = data.session;
  const who = [s.subject.age && `${s.subject.age} y`, s.subject.sex, s.subject.bmi && `BMI ${s.subject.bmi}`]
    .filter(Boolean)
    .join(' · ');

  return (
    <Layout eyebrow={`${s.source.dataset} · subject ${s.subject.id}`} title={s.label}>
      <Link to="/timeline" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Past sessions
      </Link>

      <Card>
        <CardRow>
          <div>
            <h3>Signals</h3>
            <p className="muted small">
              {who && `${who} · `}
              {s.phases.map((p) => p.name).join(' → ')}
              {s.recordedOn && ` · recorded ${s.recordedOn}`}
            </p>
          </div>
          <StatusPill>{s.quality.status}</StatusPill>
        </CardRow>

        <div className={styles.modalities}>
          {s.modalities.map((m) => (
            <span key={m.key} className={styles.modality}>
              <strong>{m.label}</strong> {m.detail}
            </span>
          ))}
        </div>

        <SyncedTracks tracks={s.tracks} phases={s.phases} durationS={s.durationS} />
        <p className="muted small">{s.quality.message}</p>
      </Card>

      {s.assessment && (
        <Card>
          <AssessmentPanel assessment={s.assessment} />
        </Card>
      )}

      <Card accent={s.fusion.verdict === 'Flagged' ? 'rose' : s.fusion.verdict === 'Watch' ? 'amber' : 'sage'}>
        <FusionPanel fusion={s.fusion} />
      </Card>

      <Card>
        <h3>By phase</h3>
        <PhaseTable metricDefs={s.metricDefs} metrics={s.metrics} />
      </Card>

      <Card>
        <h3>Preprocessing pipeline</h3>
        <PipelineTrace stages={s.pipeline} />
      </Card>

      <p className={`muted small ${styles.source}`}>
        {s.source.note}{' '}
        {s.source.url && (
          <a href={s.source.url} target="_blank" rel="noreferrer">
            Source <ExternalLink size={11} aria-hidden="true" />
          </a>
        )}
      </p>
    </Layout>
  );
}
