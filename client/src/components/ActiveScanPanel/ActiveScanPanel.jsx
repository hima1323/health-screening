import { useEffect } from 'react';
import { Wind, X } from 'lucide-react';
import { getActiveScan } from '../../api';
import useResource from '../../hooks/useResource';
import useCountdown from '../../hooks/useCountdown';
import { Card, Button, StatTile, StatusPill, Spinner, ErrorState } from '../ui';
import AuraOrb from '../AuraOrb';
import styles from './ActiveScanPanel.module.css';

const SIGNAL_TONE = {
  lighting: 'var(--sage)',
  position: 'var(--sage)',
  motion: 'var(--amber)',
  sensorStream: 'var(--sage)',
};

/** The live capture screen: step tracker, countdown orb and signal quality. */
export default function ActiveScanPanel({ sessionId, onComplete, onBack, onPhaseChange }) {
  const { data: session, error } = useResource(() => getActiveScan(sessionId), [sessionId]);
  const remaining = useCountdown(session?.progress.secondsRemaining);

  useEffect(() => {
    if (remaining === 0) onPhaseChange?.('Analysing');
  }, [remaining, onPhaseChange]);

  if (error) return <ErrorState message={error} />;
  if (!session || remaining === null) return <Spinner />;

  const { steps, currentStepIndex, progress, environment, ecgFallback } = session;
  const isDone = remaining === 0;
  const elapsed = isDone ? 1 : Math.max(0, Math.min(1, 1 - remaining / (progress.secondsRemaining || 1)));

  const signals = [
    { key: 'lighting', label: 'Lighting', value: environment.lighting },
    { key: 'position', label: 'Position', value: environment.position },
    { key: 'motion', label: 'Motion', value: environment.motion },
    { key: 'sensorStream', label: 'Signal', value: environment.sensorStream },
  ];

  return (
    <>
      <div className={styles.steps}>
        {steps.map((step, index) => (
          <div key={step} className={`${styles.step} ${index <= currentStepIndex ? styles.stepDone : ''}`.trim()}>
            <span className={styles.stepBar} />
            <span className={styles.stepLabel}>{step}</span>
          </div>
        ))}
      </div>

      <Card className={styles.focus}>
        <AuraOrb
          size={172}
          value={isDone ? 'Done' : remaining}
          caption={isDone ? 'analysing readings' : 'seconds remaining'}
          ring={{ inset: 22, progress: elapsed }}
        />

        <StatTile className={styles.guidance}>
          <p className={styles.instruction}>
            <Wind size={16} strokeWidth={1.8} aria-hidden="true" />
            {isDone ? 'Capture complete' : progress.instruction}
          </p>
          <p className="muted center">
            {isDone
              ? 'Your readings are being analysed. Your session report will be ready shortly.'
              : progress.note}
          </p>
        </StatTile>

        {isDone && (
          <div className={styles.doneActions}>
            <Button onClick={onComplete}>View session report</Button>
            <Button variant="link" onClick={onBack}>
              Back to Scan Hub
            </Button>
          </div>
        )}
      </Card>

      <Card>
        <p className="label">Signal quality</p>
        <div className="grid-two">
          {signals.map((signal) => (
            <StatTile key={signal.key} className={styles.signal}>
              <span className={styles.signalDot} style={{ background: SIGNAL_TONE[signal.key] }} aria-hidden="true" />
              <div>
                <StatTile.Label>{signal.label}</StatTile.Label>
                <p className={styles.signalValue}>{signal.value}</p>
              </div>
            </StatTile>
          ))}
        </div>
      </Card>

      {ecgFallback && (
        <Card className={styles.fallback}>
          <p>
            <strong>{ecgFallback.title}</strong> — {ecgFallback.description}
          </p>
          <StatusPill dot={false}>{ecgFallback.badge}</StatusPill>
        </Card>
      )}

      {!isDone && (
        <Button variant="link" className={styles.cancel} onClick={onBack}>
          <X size={14} aria-hidden="true" /> Cancel session
        </Button>
      )}
    </>
  );
}
