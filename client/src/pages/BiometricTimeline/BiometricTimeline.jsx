import { useState } from 'react';
import { getTimeline } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AmbientCurve from '../../components/AmbientCurve';
import ModalityLane from '../../components/ModalityLane';
import FusionPanel from '../../components/FusionPanel';
import PipelineTrace from '../../components/PipelineTrace';
import { Card, CardRow, StatTile, StatusPill, Spinner, ErrorState } from '../../components/ui';
import styles from './BiometricTimeline.module.css';

/**
 * The patient's history, as a multimodal dashboard: each sensing channel on its
 * own, what they say once fused, the preprocessing chain behind them, and the
 * log of past screenings.
 *
 * Selecting a channel anywhere filters the pipeline to the stages that produced
 * it, so the dashboard answers "where did this number come from?".
 */
export default function BiometricTimeline() {
  const { patientId } = usePrimary();
  const { data, error } = useResource(() => getTimeline(patientId), [patientId]);
  const [channel, setChannel] = useState(null);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { timeline, logs } = data;
  const { modalities = [], fusion, pipeline = [] } = timeline;

  // clicking the selected channel again clears the filter
  const select = (key) => setChannel((current) => (current === key ? null : key));

  return (
    <Layout eyebrow="Aura biometrics" title="Vitals timeline">
      {modalities.length > 0 && (
        <Card>
          <CardRow>
            <div>
              <h3>Sensing channels</h3>
              <p className="muted small">
                {modalities.length} modalities over 30 days · select one to trace it through the pipeline
              </p>
            </div>
            {channel && (
              <button type="button" className={styles.clear} onClick={() => setChannel(null)}>
                Clear filter
              </button>
            )}
          </CardRow>

          <div className={styles.lanes}>
            {modalities.map((modality) => (
              <ModalityLane
                key={modality.key}
                modality={modality}
                selected={channel === modality.key}
                onSelect={select}
              />
            ))}
          </div>
        </Card>
      )}

      {fusion && (
        <Card accent={fusion.verdict === 'Flagged' ? 'rose' : 'sage'}>
          <FusionPanel fusion={fusion} selected={channel} onSelect={select} />
        </Card>
      )}

      {pipeline.length > 0 && (
        <Card>
          <CardRow>
            <div>
              <h3>Preprocessing pipeline</h3>
              <p className="muted small">
                {channel ? 'Showing the stages behind the selected channel' : 'Every stage, in the order it runs'}
              </p>
            </div>
          </CardRow>
          <PipelineTrace stages={pipeline} highlight={channel} />
        </Card>
      )}

      <Card>
        <div>
          <h3>30-day trend</h3>
          <p className={`label tight ${styles.trendCaption}`}>Equilibrium field · heart rate</p>
        </div>

        <AmbientCurve curve={timeline.curve} />

        <div className={`grid-two ${styles.summary}`}>
          <StatTile>
            <StatTile.Label>Mean pulse</StatTile.Label>
            <StatTile.Value>
              {timeline.meanPulse} <StatTile.Unit>bpm</StatTile.Unit>
            </StatTile.Value>
          </StatTile>
          <StatTile>
            <StatTile.Label>Thermal avg</StatTile.Label>
            <StatTile.Value>
              {timeline.thermalAvg} <StatTile.Unit>°C</StatTile.Unit>
            </StatTile.Value>
          </StatTile>
        </div>
      </Card>

      <div className={styles.logsHeader}>
        <p className="label tight">Screening logs</p>
        <StatusPill dot={false}>Synced cloud</StatusPill>
      </div>

      {logs.map((log) => (
        <Card key={log._id} accent={log.status === 'Flagged' ? 'rose' : 'sage'}>
          <CardRow>
            <div>
              <p className={styles.logDate}>{log.dateLabel}</p>
              <p className={`label tight ${styles.trendCaption}`}>
                {log.location} · {log.timeLabel}
              </p>
            </div>
            <StatusPill dot={false}>{log.status}</StatusPill>
          </CardRow>

          <div className={`grid-two ${styles.summary}`}>
            <StatTile>
              <StatTile.Label>Heart rate</StatTile.Label>
              <StatTile.Value>
                {log.heartRate} <StatTile.Unit>bpm</StatTile.Unit>
              </StatTile.Value>
            </StatTile>
            <StatTile>
              <StatTile.Label>Temperature</StatTile.Label>
              <StatTile.Value>
                {log.temp} <StatTile.Unit>°C</StatTile.Unit>
              </StatTile.Value>
            </StatTile>
          </div>
        </Card>
      ))}
    </Layout>
  );
}
