import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { QrCode, ArrowRight, ListChecks } from 'lucide-react';
import { getTriageSamples, runTriage, verifyTriageCode } from '../../api';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import QrScanner from '../../components/QrScanner';
import TriageResult from '../../components/TriageResult';
import { Card, Button, Spinner, ErrorState } from '../../components/ui';
import styles from './DemoScan.module.css';

const PHASES = ['Reading the sample file', 'Checking signal quality', 'Applying the triage rules', 'Writing the explanation'];

/**
 * Reasoning-model demo for presentations, no account or database needed: scan the kiosk's demo QR (/kiosk?demo=1),
 * which carries a sample data file from MIMIC-IV-ED, Yale ED or our rPPG test videos; the server runs the rule-based
 * triage on it and this page shows the readings, the decision and why. `?sample=<id>` runs one directly.
 */
export default function DemoScan() {
  const [params, setParams] = useSearchParams();
  const [step, setStep] = useState('intro'); // intro | qr | pick | analysing | result
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [phase, setPhase] = useState(0);

  const analyse = useCallback(async (sample) => {
    setStep('analysing');
    setError(null);
    setPhase(0);
    const started = Date.now();
    try {
      const res = await runTriage(sample);
      // keep the short analysing screen visible, so the audience sees the steps
      await new Promise((r) => setTimeout(r, Math.max(0, 3200 - (Date.now() - started))));
      setResult(res);
      setStep('result');
    } catch (err) {
      setError(err.message);
      setStep('intro');
    }
  }, []);

  useEffect(() => {
    const sample = params.get('sample');
    if (sample) {
      setParams({}, { replace: true });
      analyse(sample);
    }
  }, [params, setParams, analyse]);

  useEffect(() => {
    if (step !== 'analysing') return undefined;
    const timer = setInterval(() => setPhase((p) => Math.min(p + 1, PHASES.length - 1)), 800);
    return () => clearInterval(timer);
  }, [step]);

  const again = () => {
    setResult(null);
    setStep('intro');
  };

  if (step === 'qr') {
    return (
      <Layout eyebrow="Aura Screen · demo" title="Scan the kiosk code" showTabs={false}>
        <QrScanner
          verify={verifyTriageCode}
          onScanned={(text, verified) => (verified?.sample ? analyse(verified.sample) : setStep('pick'))}
          onCancel={again}
        />
      </Layout>
    );
  }

  if (step === 'pick') return <SamplePicker onPick={analyse} onBack={again} />;

  if (step === 'analysing') {
    return (
      <Layout eyebrow="Aura Screen · demo" title="Analysing" showTabs={false}>
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

  if (step === 'result' && result) {
    return (
      <Layout eyebrow="Aura Screen · reasoning model demo" title="Your result" showTabs={false}>
        <TriageResult result={result} onAgain={again} />
      </Layout>
    );
  }

  return (
    <Layout eyebrow="Aura Screen · demo" title="Reasoning model demo" showTabs={false}>
      <Card className={styles.focus}>
        <AuraOrb size={160} value="QR" caption="sample data" />
        <p className="center">
          Scan the code on the kiosk screen. It carries a temporary sample data file (a past case from MIMIC-IV-ED,
          Yale ED or one of our rPPG test videos), and the reasoning model shows what it decides and why.
        </p>
        {error && <p className={styles.error}>{error}</p>}
        <Button onClick={() => setStep('qr')}>
          <QrCode size={16} aria-hidden="true" /> Scan the kiosk code <ArrowRight size={15} aria-hidden="true" />
        </Button>
        <Button variant="link" onClick={() => setStep('pick')}>
          <ListChecks size={14} aria-hidden="true" /> No camera? Choose a sample
        </Button>
      </Card>
    </Layout>
  );
}

function SamplePicker({ onPick, onBack }) {
  const [samples, setSamples] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    getTriageSamples().then(setSamples, (err) => setError(err.message));
  }, []);
  if (error) return <ErrorState message={error} />;
  if (!samples) return <Spinner />;
  const groups = samples.reduce((acc, s) => ({ ...acc, [s.dataset]: [...(acc[s.dataset] || []), s] }), {});
  return (
    <Layout eyebrow="Aura Screen · demo" title="Choose a sample" showTabs={false}>
      {Object.entries(groups).map(([dataset, items]) => (
        <Card key={dataset}>
          <p className="label">{dataset}</p>
          <ul className={styles.samples}>
            {items.map((s) => (
              <li key={s.id}>
                <button type="button" className={styles.sample} onClick={() => onPick(s.id)}>
                  <span className={styles.sampleTitle}>{s.title}</span>
                  <span className="muted small">{s.note}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      <Button variant="link" onClick={onBack}>
        Back
      </Button>
    </Layout>
  );
}
