import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Video, Thermometer, HeartPulse, QrCode, ArrowRight, Radar, ShieldCheck } from 'lucide-react';
import { getScanHub } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import QrScanner from '../../components/QrScanner';
import ActiveScanPanel from '../../components/ActiveScanPanel';
import InfoSheet from '../../components/InfoSheet';
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
      <Layout eyebrow="Aura Screen" title="Scan to begin" showTabs={false}>
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
        showTabs={false}
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
      <div>
        <p className={styles.greeting}>
          Hello, <strong>{patient.name}</strong>
        </p>
        <h2 className={styles.question}>How is your body feeling today?</h2>
      </div>

      <div className={`grid-two ${styles.hubGrid}`}>
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

        <div className={`stack ${styles.side}`}>
          {lastScreeningReport && (
            <Card>
              <CardRow>
                <div>
                  <h3>Last screening</h3>
                  <p className="muted small">
                    {lastScreeningReport.dateLabel}
                    <span className="wide-only"> · {lastScreeningReport.summary}</span>
                  </p>
                </div>
                <StatusPill dot={false}>{lastScreeningReport.status}</StatusPill>
              </CardRow>

              <StatTile.Row className={styles.lastTiles}>
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
            <Card className="wide-only">
              <p className="label">What the station captures</p>
              <Captures captures={station.captures} />
            </Card>
          )}

          <Card className={`wide-only ${styles.consent}`}>
            <p className="label">Consent summary</p>
            <p className="muted">{consent.text}</p>
          </Card>

          {/* phones: the same detail, one tap away instead of a long scroll */}
          <div className="phone-only">
            <div className={styles.sheets}>
              {station && (
                <InfoSheet
                  icon={Radar}
                  label="How it works"
                  hint={`${station.captures.length} sensors`}
                  title="What the station captures"
                >
                  <Captures captures={station.captures} />
                </InfoSheet>
              )}
              <InfoSheet icon={ShieldCheck} label="Consent" hint={consent.givenDate && `Given ${consent.givenDate}`} title="Consent summary">
                <p>{consent.text}</p>
              </InfoSheet>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}

function Captures({ captures }) {
  return (
    <ul className={styles.captures}>
      {captures.map((capture) => {
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
  );
}
