import { getTimeline, getStudySessions } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AmbientCurve from '../../components/AmbientCurve';
import SessionCard from '../../components/SessionCard';
import { Card, CardRow, StatTile, StatusPill, Spinner, ErrorState } from '../../components/ui';
import styles from './BiometricTimeline.module.css';

/** Group sessions by the dataset they came from, keeping the server's order. */
function byDataset(sessions) {
  const groups = new Map();
  sessions.forEach((s) => {
    if (!groups.has(s.source.dataset)) groups.set(s.source.dataset, []);
    groups.get(s.source.dataset).push(s);
  });
  return [...groups.entries()];
}

/**
 * The history: the patient's own trend and screening log, then every past
 * study session — each opens into its multimodal analysis.
 */
export default function BiometricTimeline() {
  const { patientId } = usePrimary();
  const { data, error } = useResource(() => getTimeline(patientId), [patientId]);
  const { data: study, error: studyError } = useResource(getStudySessions, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { timeline, logs } = data;

  return (
    <Layout eyebrow="Aura biometrics" title="Vitals timeline">
      <Card className={styles.trend}>
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

      <Card>
        <CardRow>
          <div>
            <h3>Past sessions</h3>
            <p className="muted small">
              Recorded study sessions · open one for its multimodal analysis
            </p>
          </div>
        </CardRow>

        {studyError && <p className="muted">{studyError}</p>}
        {!study && !studyError && <Spinner />}
        {study &&
          byDataset(study.sessions).map(([dataset, sessions]) => (
            <section key={dataset} className={styles.dataset}>
              <p className="label">
                {dataset} · {sessions.length} session{sessions.length > 1 ? 's' : ''}
              </p>
              <div className={styles.sessions}>
                {sessions.map((s) => (
                  <SessionCard key={s.sessionKey} session={s} />
                ))}
              </div>
            </section>
          ))}
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
