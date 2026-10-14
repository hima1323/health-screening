import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronDown, Download, ExternalLink } from 'lucide-react';
import { getStudySession } from '../../api';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import ReadingsSummary from '../../components/ReadingsSummary';
import AssessmentPanel from '../../components/AssessmentPanel';
import SyncedTracks from '../../components/SyncedTracks';
import ThermalViewer from '../../components/ThermalViewer';
import PhaseTable from '../../components/PhaseTable';
import { formatDate, sessionId } from '../../components/SessionCard';
import Backdrop from './Backdrop';
import HeroBanner from './HeroBanner';
import { Card, Spinner, ErrorState } from '../../components/ui';
import { downloadJson } from '../../utils/download';
import styles from './SessionAnalysis.module.css';

/** The model's own labels, in words a patient reads; anything not listed keeps its label. */
const PLAIN = {
  'Fused P(high load)': 'Mental effort, all sensors (0–1)',
  'Face (action units)': 'Mental effort, from your face',
  'Eye tracker': 'Mental effort, from your eyes',
  'n-back level': 'Task difficulty (1–3)',
  'Mean P(high load)': 'Average mental effort (0–1)',
  'Windows called high': 'Moments read as high effort',
};
const plain = (label) => PLAIN[label] ?? label;

/**
 * One past session for the patient. On the first screen: how many readings are fine, each reading against its
 * normal range with what it means, and the session at a glance; below, how each part went and, collapsed, all the
 * data. A white page with soft colour washes behind the cards. (Chosen over a concise version in the Lab 9 A/B test.)
 */
export default function SessionAnalysis() {
  const { key } = useParams();
  const { data, error } = useResource(() => getStudySession(key), [key]);
  // one clock shared by the thermal viewer and the signal graph
  const [time, setTime] = useState(null);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const s = data.session;
  const minutes = Math.round(s.durationS / 60);
  const points = s.tracks.reduce((n, t) => n + t.values.length, 0);
  const tracks = s.tracks.map((t) => ({ ...t, label: plain(t.label) }));
  const metricDefs = s.metricDefs.map((d) => ({ ...d, label: plain(d.label) }));

  return (
    <Layout eyebrow={`Session ${sessionId(s.sessionKey)} · ${formatDate(s.recordedOn)}`} title={s.label}>
      <Backdrop />
      {s.simulationNote && <p className={styles.prototype}>{s.simulationNote}</p>}

      <Link to="/timeline" className={styles.back}>
        <ArrowLeft size={14} aria-hidden="true" /> Past sessions
      </Link>

      {s.summary?.readings?.length > 0 && (
        <HeroBanner readings={s.summary.readings} minutes={minutes} sensors={s.modalities.length} />
      )}

      {s.summary?.readings?.length > 0 && (
        <Card>
          <ReadingsSummary summary={s.summary} advice={s.assessment?.advice} detailed />
        </Card>
      )}

      <Card>
        <h3>This session at a glance</h3>
        <dl className={styles.glance}>
          <div>
            <dt>{minutes} min</dt>
            <dd>How long you were recorded</dd>
          </div>
          <div>
            <dt>{s.modalities.length}</dt>
            <dd>Sensors used: {s.modalities.map((m) => m.label).join(', ')}</dd>
          </div>
          <div>
            <dt>{s.phases.length}</dt>
            <dd>Parts of the session: {s.phases.map((p) => p.name).join(', ')}</dd>
          </div>
          <div>
            <dt>{points.toLocaleString()}</dt>
            <dd>Measurements behind these results</dd>
          </div>
        </dl>
        <p className="muted small">
          Signal quality: {s.quality.status}. One recording is a snapshot of that day, not a diagnosis.
        </p>
      </Card>

      {s.assessment && (
        <Card>
          <h3>How each part of the session went</h3>
          {s.reasoning?.conclusion && <p className="muted small">{s.reasoning.conclusion}</p>}
          {/* the doctor question is already answered above */}
          <AssessmentPanel assessment={{ ...s.assessment, advice: null }} />
        </Card>
      )}

      {/* collapsed: the readings above answer the question; the raw data is there for whoever wants it */}
      <details className={styles.full}>
        <summary className={styles.fullToggle}>
          <span>
            <strong>Show all your data</strong>
            <small>
              {points.toLocaleString()} measurements from {s.modalities.length} sensors, as charts and a table
            </small>
          </span>
          <ChevronDown size={16} aria-hidden="true" className={styles.chevron} />
        </summary>

        <Card>
          <p className="muted small">
            Each line is one measurement over time; the shaded bands are the parts of the session. Drag across the chart
            to read every line at the same moment.
          </p>

          {s.frames && (
            <ThermalViewer
              sessionKey={s.sessionKey}
              frames={s.frames}
              rois={s.rois}
              tracks={tracks}
              time={time}
              onTime={setTime}
            />
          )}

          <SyncedTracks
            tracks={tracks}
            phases={s.phases}
            durationS={s.durationS}
            time={s.frames ? time : null}
            onScrub={s.frames ? setTime : undefined}
          />

          <PhaseTable metricDefs={metricDefs} metrics={s.metrics} />

          <button type="button" className={styles.back} onClick={() => downloadJson(s, `${s.sessionKey}.json`)}>
            <Download size={14} aria-hidden="true" /> Download all data
          </button>
        </Card>
      </details>

      <p className="muted small">Your doctor sees the full analysis. A screening aid, not a diagnosis.</p>

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
