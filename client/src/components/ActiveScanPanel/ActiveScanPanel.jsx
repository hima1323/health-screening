import { useEffect, useRef, useState } from 'react';
import { Check, CircleAlert, Loader, X } from 'lucide-react';
import { getScan, startScan } from '../../api';
import { Card, Button, StatTile } from '../ui';
import AuraOrb from '../AuraOrb';
import styles from './ActiveScanPanel.module.css';
import usePrefs from '../../hooks/usePrefs';

const STAGES = ['linked', 'capturing', 'uploading', 'analysing', 'done'];
const POLL_MS = 800;
// the server can pass several stages between two polls; each is shown at least this long so it can be read
const MIN_STAGE_MS = 900;

/**
 * The live capture screen. Starts the scan with the kiosk code the phone just read, then follows it on the
 * server: the station captures, sends the sample to the model server, the model answers, a report is written.
 */
export default function ActiveScanPanel({ code, stationLabel = 'Station 2', onComplete, onBack, onPhaseChange }) {
  const { t } = usePrefs();
  const [scan, setScan] = useState(null);
  const [error, setError] = useState(null);
  const [shown, setShown] = useState(0); // index into STAGES, trailing the server by at most MIN_STAGE_MS a step
  const now = useNow(250);
  const started = useRef(null); // one start per screen, even when React mounts the effect twice

  // start once, then poll
  useEffect(() => {
    let timer;
    let active = true;
    const poll = (id) => {
      timer = setTimeout(async () => {
        try {
          const { scan: next } = await getScan(id);
          if (!active) return;
          setScan(next);
          if (next.stage !== 'done' && next.stage !== 'failed') poll(id);
        } catch (err) {
          if (active) setError(err.message);
        }
      }, POLL_MS);
    };
    started.current ??= startScan(code);
    started.current.then(
      ({ scan: first }) => {
        if (!active) return;
        setScan(first);
        poll(first.id);
      },
      (err) => active && setError(err.message)
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [code]);

  const target = scan ? (scan.stage === 'failed' ? shown : STAGES.indexOf(scan.stage)) : 0;
  const lastStep = useRef(0);
  useEffect(() => {
    if (shown >= target) return undefined;
    const wait = Math.max(0, lastStep.current + MIN_STAGE_MS - Date.now());
    const timer = setTimeout(() => {
      lastStep.current = Date.now();
      setShown((s) => s + 1);
    }, wait);
    return () => clearTimeout(timer);
  }, [shown, target]);

  const stage = STAGES[shown];
  const failed = error || (scan?.stage === 'failed' && scan.error);
  useEffect(() => {
    onPhaseChange?.(failed ? 'Failed' : { capturing: 'Capturing', uploading: 'Uploading', analysing: 'Analysing', done: 'Done' }[stage] ?? 'Linked');
  }, [stage, failed, onPhaseChange]);

  const captureStart = scan?.stages?.capturing && new Date(scan.stages.capturing).getTime();
  const remaining =
    stage === 'capturing' && captureStart
      ? Math.max(0, Math.ceil(scan.captureSeconds - (now - captureStart) / 1000))
      : null;
  const elapsed = shown > 1 ? 1 : remaining == null ? 0 : 1 - remaining / scan.captureSeconds;

  const steps = [
    { key: 'linked', label: `Linked to ${stationLabel}`, detail: 'The kiosk code was verified by the server.' },
    {
      key: 'capturing',
      label: 'Station capturing',
      detail: scan?.sample ? `Demo station sends a demo case: ${scan.sample.task}` : 'Reading your signals.',
    },
    {
      key: 'uploading',
      label: 'Sending the case to the reasoning model',
      detail: 'Readings and answers go to the triage expert system.',
    },
    {
      key: 'analysing',
      label: 'Model analysing',
      detail: scan?.upload
        ? `The triage rules answered in ${scan.upload.modelMs} ms.`
        : 'Applying the triage rules and writing the explanation.',
    },
  ];

  return (
    <>
      <div className={styles.steps}>
        {STAGES.slice(0, 4).map((key, index) => (
          <div key={key} className={`${styles.step} ${index <= shown ? styles.stepDone : ''}`.trim()}>
            <span className={styles.stepBar} />
            <span className={styles.stepLabel}>{t(['Linked', 'Capture', 'Upload', 'Analyse'][index])}</span>
          </div>
        ))}
      </div>

      <Card className={styles.focus}>
        <AuraOrb
          size={172}
          value={failed ? '!' : stage === 'done' ? t('Done') : remaining ?? '…'}
          caption={
            failed ? 'scan stopped' : stage === 'done' ? 'results ready' : remaining != null ? 'seconds remaining' : t(steps[shown]?.label ?? '')
          }
          ring={{ inset: 22, progress: elapsed }}
        />

        <StatTile className={styles.guidance}>
          <p className={styles.instruction}>
            {t(
              failed
                ? 'The scan could not finish'
                : stage === 'done'
                  ? 'Your results are ready'
                  : stage === 'capturing'
                    ? 'Hold still and breathe normally'
                    : 'Analysing your readings'
            )}
          </p>
          <p className="muted center">
            {t(
              failed ||
                (stage === 'done'
                  ? 'The model has read your capture and written your session report.'
                  : 'Stay near the station until the capture finishes.')
            )}
          </p>
        </StatTile>

        {(stage === 'done' || failed) && (
          <div className={styles.doneActions}>
            {stage === 'done' && !failed && (
              <Button onClick={() => onComplete(scan.sessionId)}>{t('View session report')}</Button>
            )}
            <Button variant={failed ? 'primary' : 'link'} onClick={onBack}>
              {t(failed ? 'Back to Scan Hub and try again' : 'Back to Scan Hub')}
            </Button>
          </div>
        )}
      </Card>

      <Card>
        <p className={`label ${styles.signalsLabel}`}>{t('What is happening')}</p>
        <ol className={styles.pipeline}>
          {steps.map((step, index) => {
            const state = index < shown || stage === 'done' ? 'done' : index === shown ? (failed ? 'failed' : 'active') : 'waiting';
            const Icon = { done: Check, active: Loader, failed: CircleAlert }[state];
            return (
              <li key={step.key} className={styles[state]}>
                <span className={styles.pipelineIcon} aria-hidden="true">
                  {Icon && <Icon size={14} strokeWidth={2} />}
                </span>
                <div>
                  <p className={styles.pipelineLabel}>{t(step.label)}</p>
                  {state !== 'waiting' && <p className="muted small">{t(step.detail)}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      {stage !== 'done' && !failed && (
        <Button variant="link" className={styles.cancel} onClick={onBack}>
          <X size={14} aria-hidden="true" /> {t('Leave this screen')}
        </Button>
      )}
    </>
  );
}

/** The current time, refreshed every `ms` — drives the capture countdown from the server's timestamps. */
function useNow(ms) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}
