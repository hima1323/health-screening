import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, ExternalLink } from 'lucide-react';
import { getDoctorPatientSession } from '../../api';
import useResource from '../../hooks/useResource';
import SyncedTracks from '../../components/SyncedTracks';
import ThermalViewer from '../../components/ThermalViewer';
import PhaseTable from '../../components/PhaseTable';
import FusionPanel from '../../components/FusionPanel';
import PipelineTrace from '../../components/PipelineTrace';
import AssessmentPanel from '../../components/AssessmentPanel';
import ReadingsSummary from '../../components/ReadingsSummary';
import { formatDate, sessionId } from '../../components/SessionCard';
import { Card, CardRow, StatusPill, Spinner, ErrorState } from '../../components/ui';
import { downloadJson } from '../../utils/download';
import patientStyles from './DoctorPatient.module.css';
import styles from './DoctorSession.module.css';

/**
 * One recorded session of a patient, for the doctor: first what the model says (the patient's result, the
 * per-phase findings, how each sensor agent voted, the reasoning window by window), then all the original data.
 */
export default function DoctorSession() {
  const { patientId, key } = useParams();
  const { data, error } = useResource(() => getDoctorPatientSession(patientId, key), [patientId, key]);
  // one clock shared by the thermal viewer and the signal graph
  const [time, setTime] = useState(null);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { session: s, patient } = data;

  return (
    <>
      <div className={patientStyles.head}>
        <Link to={`/doctor/patients/${patientId}`} className={patientStyles.back}>
          <ArrowLeft size={14} aria-hidden="true" /> {patient.name}
        </Link>
        <h1 className={patientStyles.title}>{s.label}</h1>
        <p className="muted small">
          {patient.name}, {patient.age} · session {sessionId(s.sessionKey)} · {formatDate(s.recordedOn)} ·{' '}
          {s.source.dataset}
          {s.subject?.id && ` subject ${s.subject.id}`}
        </p>
      </div>

      {s.simulationNote && <p className={styles.prototype}>{s.simulationNote}</p>}

      <h2 className={styles.section}>What the model says</h2>
      <div className="stack">
        {s.summary?.readings?.length > 0 && (
          <Card>
            <p className="label">The patient&rsquo;s result, as they see it</p>
            <ReadingsSummary summary={s.summary} advice={s.assessment?.advice} />
          </Card>
        )}

        {s.assessment && (
          <Card>
            <p className="label">Findings</p>
            <AssessmentPanel assessment={s.assessment} />
          </Card>
        )}

        <Card accent={s.fusion.verdict === 'Flagged' ? 'rose' : s.fusion.verdict === 'Watch' ? 'amber' : 'calm'}>
          <FusionPanel fusion={s.fusion} />
        </Card>

        {s.reasoning?.steps?.length > 0 && <Reasoning steps={s.reasoning.steps} />}
      </div>

      <CardRow>
        <h2 className={styles.section}>Original data</h2>
        <button type="button" className={`${patientStyles.back} ${styles.download}`} onClick={() => downloadJson(s, `${s.sessionKey}.json`)}>
          <Download size={14} aria-hidden="true" /> Download all data (JSON)
        </button>
      </CardRow>
      <div className="stack">
        <Card>
          <CardRow>
            <div>
              <h3>Signals</h3>
              <p className="muted small">{s.phases.map((p) => p.name).join(' → ')}</p>
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

        <Card>
          <h3>Every metric by phase</h3>
          <PhaseTable metricDefs={s.metricDefs} metrics={s.metrics} />
        </Card>

        {s.pipeline?.length > 0 && (
          <Card>
            <h3>Preprocessing pipeline</h3>
            <PipelineTrace stages={s.pipeline} />
          </Card>
        )}
      </div>

      <p className={`muted small ${styles.source}`}>
        {s.source.note}{' '}
        {s.source.url && (
          <a href={s.source.url} target="_blank" rel="noreferrer">
            Source <ExternalLink size={11} aria-hidden="true" />
          </a>
        )}
      </p>
    </>
  );
}

/** How the conclusion follows from the numbers: each step says what was checked, what it showed, and what that means. */
function Reasoning({ steps }) {
  return (
    <Card>
      <h3>How the model got there</h3>
      <p className="muted small">One explained window per phase, written by the LLM and checked against the data</p>
      <ol className={styles.steps}>
        {steps.map((step) => (
          <li key={step.look} className={styles.step}>
            <p className={styles.stepLook}>{step.look}</p>
            {step.found && <p className={styles.stepFound}>{step.found}</p>}
            {step.groups?.map((group) => (
              <div key={group.heading} className={styles.stepGroup}>
                <p className={styles.groupHeading}>{group.heading}</p>
                <ul className={styles.groupItems}>
                  {group.items.map((item) => (
                    <li key={item.label + item.text}>
                      <strong>{item.label}</strong> · {item.text}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <p className={styles.stepSo}>→ {step.so}</p>
          </li>
        ))}
      </ol>
    </Card>
  );
}
