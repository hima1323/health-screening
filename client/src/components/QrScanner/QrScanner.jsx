import { useEffect, useState } from 'react';
import { ScanLine, CameraOff, Check, ShieldAlert } from 'lucide-react';
import { verifyStationCode } from '../../api';
import useQrScanner from '../../hooks/useQrScanner';
import { Sheet } from '../InfoSheet';
import { Card, Button } from '../ui';
import styles from './QrScanner.module.css';

const HEADLINE = {
  starting: 'Waking the camera…',
  scanning: 'Point your camera at the station QR code',
  checking: 'Checking the code…',
  found: 'Station verified',
  failed: 'The camera could not start',
};

const BODY = {
  starting: 'Allow camera access when your browser asks.',
  scanning: 'Hold steady — this connects your session to the station automatically.',
  checking: 'Making sure it comes from an Aura Screen kiosk.',
  failed: 'You can still continue — staff will link your session at the station.',
};

/** Why the scan could not start, and what the patient can do about it. */
const FAILURES = {
  blocked: {
    title: 'Camera blocked by the browser',
    why: 'Camera access was denied for this site.',
    fix: [
      'Tap the camera or lock icon in the address bar.',
      'Set Camera to “Allow” for this site.',
      'Come back here and tap Try again.',
    ],
  },
  insecure: {
    title: 'Page is not secure',
    why: 'Browsers only allow the camera on secure (https://) pages.',
    fix: ['Open the app from its https:// address, or from localhost on this computer.'],
  },
  missing: {
    title: 'No camera found',
    why: 'This device has no camera the browser can reach.',
    fix: ['Connect a camera, or use a phone or laptop that has one.', 'Then tap Try again.'],
  },
  busy: {
    title: 'Camera is in use',
    why: 'Another app or tab is already using the camera.',
    fix: ['Close video calls, other camera apps or tabs.', 'Then tap Try again.'],
  },
  unsupported: {
    title: 'Browser can’t use the camera',
    why: 'This browser does not support camera access.',
    fix: ['Open the app in an up-to-date Chrome, Safari, Edge or Firefox.'],
  },
  unknown: {
    title: 'Camera could not start',
    why: 'Something unexpected stopped the camera.',
    fix: ['Tap Try again.', 'If it keeps happening, reload the page or restart the browser.'],
  },
};

/** Live camera viewfinder that decodes the station QR code. */
export default function QrScanner({ station = 'Station 2', onScanned, onCancel }) {
  // only codes our own kiosks generate are accepted — the server checks the signature
  const { state, failure, rejection, videoRef, canvasRef, retry, skip } = useQrScanner({
    onDecode: onScanned,
    verify: verifyStationCode,
  });
  const [dialogOpen, setDialogOpen] = useState(false);

  // open the error dialog each time the camera fails
  useEffect(() => setDialogOpen(state === 'failed'), [state]);

  const isScanning = state === 'starting' || state === 'scanning' || state === 'checking';
  const cameraFailed = state === 'failed';
  const body = state === 'found' ? 'Starting your contactless scan…' : BODY[state];
  const info = cameraFailed && FAILURES[failure?.reason ?? 'unknown'];

  return (
    <Card className={styles.card}>
      <p className="label center tight">{station}</p>

      <div className={styles.body}>
        <div className={`${styles.viewfinder} ${state === 'found' ? styles.locked : ''}`.trim()}>
          <video ref={videoRef} className={styles.video} playsInline muted aria-label="Camera preview" />
          <canvas ref={canvasRef} className={styles.canvas} />

          <span className={`${styles.corner} ${styles.cornerTl}`} />
          <span className={`${styles.corner} ${styles.cornerTr}`} />
          <span className={`${styles.corner} ${styles.cornerBl}`} />
          <span className={`${styles.corner} ${styles.cornerBr}`} />

          {isScanning && <span className={styles.laser} />}
          {state === 'found' && (
            <span className={styles.result} aria-hidden="true">
              <Check size={40} strokeWidth={1.6} />
            </span>
          )}
          {cameraFailed && (
            <span className={styles.result} aria-hidden="true">
              <CameraOff size={40} strokeWidth={1.3} />
            </span>
          )}
        </div>

        <p className={styles.headline}>
          <ScanLine size={16} strokeWidth={1.8} aria-hidden="true" />
          {cameraFailed ? info.title : HEADLINE[state]}
        </p>
        <p className="muted center">{body}</p>
        {rejection && state === 'scanning' && (
          <p className={styles.rejection} role="alert">
            <ShieldAlert size={15} strokeWidth={1.8} aria-hidden="true" />
            {rejection}
          </p>
        )}
        {cameraFailed && !dialogOpen && (
          <Button variant="link" onClick={() => setDialogOpen(true)}>
            Why, and how to fix it
          </Button>
        )}
      </div>

      {/* actions sit at the bottom of the screen, within thumb reach */}
      <div className={styles.actions}>
        {cameraFailed && <Button onClick={skip}>Continue without camera</Button>}
        {cameraFailed && (
          <Button variant="link" onClick={retry}>
            Try again
          </Button>
        )}
        <Button variant="link" onClick={onCancel}>
          Cancel
        </Button>
      </div>

      {cameraFailed && dialogOpen && (
        <Sheet title={info.title} role="alertdialog" onClose={() => setDialogOpen(false)}>
          <p className={styles.why}>{info.why}</p>
          <p className={`label ${styles.fixLabel}`}>How to fix it</p>
          <ol className={styles.fix}>
            {info.fix.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {failure?.name && (
            <p className={styles.errorCode}>
              Error log · {failure.name}
              {failure.message ? ` — ${failure.message}` : ''}
            </p>
          )}
          <div className={styles.dialogActions}>
            <Button onClick={skip}>Continue without camera</Button>
            <Button variant="link" onClick={retry}>
              Try again
            </Button>
          </div>
        </Sheet>
      )}
    </Card>
  );
}
