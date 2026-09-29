import { getStudySessions } from '../../api';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import SessionCard from '../../components/SessionCard';
import { Card, Spinner, ErrorState } from '../../components/ui';
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

/** Every past session; each opens into its multimodal analysis. */
export default function BiometricTimeline() {
  const { data, error } = useResource(getStudySessions, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  return (
    <Layout eyebrow="Aura biometrics" title="Past sessions">
      <p className="muted">
        {data.sessions.length} recorded sessions · open one to see all of its signals, what they indicate, and
        whether to see a doctor.
      </p>

      {byDataset(data.sessions).map(([dataset, sessions]) => (
        <Card key={dataset}>
          <p className="label">
            {dataset} · {sessions.length} session{sessions.length > 1 ? 's' : ''}
          </p>
          <div className={styles.sessions}>
            {sessions.map((s) => (
              <SessionCard key={s.sessionKey} session={s} />
            ))}
          </div>
        </Card>
      ))}
    </Layout>
  );
}
