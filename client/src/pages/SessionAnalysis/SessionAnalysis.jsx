import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink, ChevronDown } from 'lucide-react';
import { getStudySession } from '../../api';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import SyncedTracks from '../../components/SyncedTracks';
import ThermalViewer from '../../components/ThermalViewer';
import PhaseTable from '../../components/PhaseTable';
import FusionPanel from '../../components/FusionPanel';
import PipelineTrace from '../../components/PipelineTrace';
import AssessmentPanel from '../../components/AssessmentPanel';
import { formatDate, sessionId } from '../../components/SessionCard';
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
  // one clock shared by the thermal viewer and the signal graph
  const [time, setTime] = useState(null);
  const [showFull, setShowFull] = useState(false);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const s = data.session;

  return (
    <Layout eyebrow={`Session ${sessionId(s.sessionKey)} · ${formatDate(s.recordedOn)}`} title={s.label}>
      {s.simulationNote && <p className={styles.prototype}>{s.simulationNote}</p>}

      <Link to="/timeline" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Past sessions
      </Link>

      {s.reasoning && <Reasoning reasoning={s.reasoning} verdict={s.assessment?.advice} />}

      {/* the detail stays one tap away; it only mounts when opened, so the thermal frames load on demand */}
      <details className={styles.full} onToggle={(e) => setShowFull(e.currentTarget.open)}>
        <summary className={styles.fullToggle}>
          {showFull ? 'Hide' : 'Show'} the full analysis
          <ChevronDown size={15} aria-hidden="true" className={styles.chevron} />
        </summary>
        {showFull && (
          <div className="stack">
          <Card>
            <CardRow>
              <div>
                <h3>Signals</h3>
                <p className="muted small">
                  {s.phases.map((p) => p.name).join(' → ')}
                </p>
              </div>
              <StatusPill>{s.quality.status}</StatusPill>
            </CardRow>

            <div className={styles.modalities}>
              {s.modalities.map((m) => (
                <span key={m.key} className={`${styles.modality} ${m.simulated ? styles.simulatedModality : ''}`.trim()}>
                  <strong>{m.label}</strong> {m.detail}
                </span>
              ))}
            </div>

            {s.frames && (
              <ThermalViewer
                sessionKey={s.sessionKey}
                frames={s.frames}
                rois={s.rois}
                tracks={s.tracks}
                time={time}
                onTime={setTime}
              />
            )}

            <SyncedTracks
              tracks={s.tracks}
              phases={s.phases}
              durationS={s.durationS}
              time={s.frames ? time : null}
              onScrub={s.frames ? setTime : undefined}
            />
            <p className="muted small">{s.quality.message}</p>
          </Card>

          {s.assessment && (
            <Card>
              <AssessmentPanel assessment={s.assessment} />
            </Card>
          )}

          <Card accent={s.fusion.verdict === 'Flagged' ? 'rose' : s.fusion.verdict === 'Watch' ? 'amber' : 'calm'}>
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

          </div>
        )}
      </details>

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

/** How the conclusion follows from the numbers: each step says what was checked, what it showed, and what that means. */
function Reasoning({ reasoning, verdict }) {
  return (
    <Card accent={verdict?.level === 'ok' ? 'calm' : verdict?.level === 'na' ? undefined : 'amber'}>
      <CardRow>
        <h3>What this session shows</h3>
        {verdict && <StatusPill dot={false}>{`See a doctor? ${verdict.answer}`}</StatusPill>}
      </CardRow>
      <p className={styles.conclusion}>{reasoning.conclusion}</p>

      <p className={`label ${styles.howLabel}`}>How we got there</p>
      <ol className={styles.steps}>
        {reasoning.steps.map((step) => (
          <li key={step.look} className={styles.step}>
            <p className={styles.stepLook}>{step.look}</p>
            <p className={styles.stepFound}>{step.found}</p>
            <p className={styles.stepSo}>→ {step.so}</p>
          </li>
        ))}
      </ol>
      <p className="muted small">A screening aid, not a diagnosis.</p>
    </Card>
  );
}
