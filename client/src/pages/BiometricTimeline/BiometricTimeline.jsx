import { getTimeline } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AmbientCurve from '../../components/AmbientCurve';
import { Card, CardRow, StatTile, StatusPill, Spinner, ErrorState } from '../../components/ui';
import styles from './BiometricTimeline.module.css';

/** The patient's screening history: a 30-day trend plus every logged scan. */
export default function BiometricTimeline() {
  const { patientId } = usePrimary();
  const { data, error } = useResource(() => getTimeline(patientId), [patientId]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { timeline, logs } = data;

  return (
    <Layout eyebrow="Aura biometrics" title="Vitals timeline">
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
