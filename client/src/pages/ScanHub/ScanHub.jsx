import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Video, Thermometer, HeartPulse, QrCode, ArrowRight } from 'lucide-react';
import { getScanHub } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import QrScanner from '../../components/QrScanner';
import ActiveScanPanel from '../../components/ActiveScanPanel';
import { Card, CardRow, Button, StatTile, StatusPill, Spinner, ErrorState } from '../../components/ui';
import styles from './ScanHub.module.css';

const CAPTURE_ICONS = { video: Video, thermal: Thermometer, ecg: HeartPulse };

/** The patient's home screen, and the entry point into a contactless scan. */
export default function ScanHub() {
  const { patientId, sessionId } = usePrimary();
  const navigate = useNavigate();
  const { data, error } = useResource(() => getScanHub(patientId), [patientId]);

  const [step, setStep] = useState('hub'); // hub | qr | scanning
  const [scanPhase, setScanPhase] = useState('Capturing');

  const returnToHub = () => {
    setScanPhase('Capturing');
    setStep('hub');
  };

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { patient, aura, consent, station, lastScreeningReport } = data;

  if (step === 'qr') {
    return (
      <Layout eyebrow="Aura Screen" title="Scan to begin">
        <QrScanner onScanned={() => setStep('scanning')} onCancel={returnToHub} />
      </Layout>
    );
  }

  if (step === 'scanning') {
    return (
      <Layout
        eyebrow={`Session ${sessionId} · Station 2`}
        title="Active session"
        badge={<StatusPill>{scanPhase}</StatusPill>}
      >
        <ActiveScanPanel
          sessionId={sessionId}
          onComplete={() => navigate('/report')}
          onPhaseChange={setScanPhase}
          onBack={returnToHub}
        />
      </Layout>
    );
  }

  return (
    <Layout
      eyebrow="Aura Screen"
      title="Scan Hub"
      badge={
        <span className={styles.chip}>Age {patient.age}</span>
      }
    >
      <p className={styles.greeting}>
        Hello, <strong>{patient.name}</strong>
      </p>
      <h2 className={styles.question}>How is your body feeling today?</h2>

      <div className="grid-two">
        <Card className={styles.auraCard}>
          <StatusPill>{`Biometric aura · ${aura.status}`}</StatusPill>
          {lastScreeningReport && (
            <AuraOrb size={184} value={lastScreeningReport.pulse} caption="bpm · last read" />
          )}
          <p className={styles.note}>{aura.note}</p>
          <Button onClick={() => setStep('qr')}>
            <QrCode size={16} aria-hidden="true" /> Begin contactless scan
            <ArrowRight size={15} aria-hidden="true" />
          </Button>
        </Card>

        <div className="stack">
          {lastScreeningReport && (
            <Card>
              <CardRow>
                <div>
                  <h3>Last screening</h3>
                  <p className="muted small">
                    {lastScreeningReport.dateLabel} · {lastScreeningReport.summary}
                  </p>
                </div>
                <StatusPill dot={false}>{lastScreeningReport.status}</StatusPill>
              </CardRow>

              <StatTile.Row>
                <StatTile>
                  <StatTile.Value>{lastScreeningReport.pulse}</StatTile.Value>
                  <StatTile.Label>Pulse</StatTile.Label>
                </StatTile>
                <StatTile>
                  <StatTile.Value>{lastScreeningReport.temp}°</StatTile.Value>
                  <StatTile.Label>Temp</StatTile.Label>
                </StatTile>
                <StatTile>
                  <StatTile.Value>{lastScreeningReport.breath}</StatTile.Value>
                  <StatTile.Label>Resp</StatTile.Label>
                </StatTile>
              </StatTile.Row>
            </Card>
          )}

          {station && (
            <Card>
              <p className="label">What the station captures</p>
              <ul className={styles.captures}>
                {station.captures.map((capture) => {
                  const Icon = CAPTURE_ICONS[capture.icon];
                  return (
                    <li key={capture.title}>
                      {Icon && <Icon size={19} strokeWidth={1.6} aria-hidden="true" />}
                      <div>
                        <p className={styles.captureTitle}>{capture.title}</p>
                        <p className="muted">{capture.description}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}

          <Card>
            <p className="label">Consent summary</p>
            <p className="muted">{consent.text}</p>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
