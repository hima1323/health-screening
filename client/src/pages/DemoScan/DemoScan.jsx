import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { runTriage } from '../../api';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import TriageResult from '../../components/TriageResult';
import { Card, Button } from '../../components/ui';
import styles from './DemoScan.module.css';

const PHASES = ['Reading your measurements', 'Checking signal quality', 'Applying the triage rules', 'Writing the explanation'];

/**
 * The reasoning model's result for a scanned case (/result). The Scan Hub opens it, passing the case id in the
 * navigation state, when the patient scans a printed case QR (server/scripts/demo-qr.js); the server runs the
 * rule-based triage on that case and this page shows the readings, the decision and why.
 */
export default function DemoScan() {
  const sample = useLocation().state?.sample;
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (!sample) return undefined;
    let active = true;
    const started = Date.now();
    runTriage(sample).then(
      // keep the short analysing screen visible, so the audience sees the steps
      (res) => setTimeout(() => active && setResult(res), Math.max(0, 3200 - (Date.now() - started))),
      (err) => active && setError(err.message)
    );
    return () => {
      active = false;
    };
  }, [sample]);

  useEffect(() => {
    if (result || error) return undefined;
    const timer = setInterval(() => setPhase((p) => Math.min(p + 1, PHASES.length - 1)), 800);
    return () => clearInterval(timer);
  }, [result, error]);

  if (!sample) return <Navigate to="/" replace />;
  const home = () => navigate('/');

  if (error) {
    return (
      <Layout eyebrow="Aura Screen" title="Could not analyse" showTabs={false}>
        <Card className={styles.focus}>
          <p className={styles.error}>{error}</p>
          <Button onClick={home}>Back to the Scan Hub</Button>
        </Card>
      </Layout>
    );
  }

  if (result) {
    return (
      <Layout eyebrow="Aura Screen · reasoning model" title="Your result" showTabs={false}>
        <TriageResult result={result} onAgain={home} />
      </Layout>
    );
  }

  return (
    <Layout eyebrow="Aura Screen · reasoning model" title="Analysing" showTabs={false}>
      <Card className={styles.focus}>
        <AuraOrb size={172} value="···" caption={PHASES[phase]} ring={{ inset: 22, progress: (phase + 1) / PHASES.length }} />
        <ol className={styles.phases}>
          {PHASES.map((p, i) => (
            <li key={p} className={i <= phase ? styles.done : ''}>
              {p}
            </li>
          ))}
        </ol>
      </Card>
    </Layout>
  );
}
