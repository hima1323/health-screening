import { ScanLine, CameraOff, Check } from 'lucide-react';
import useQrScanner from '../../hooks/useQrScanner';
import { Card, Button } from '../ui';
import styles from './QrScanner.module.css';

const HEADLINE = {
  starting: 'Waking the camera…',
  scanning: 'Point your camera at the station QR code',
  found: 'QR code recognised',
  denied: 'Camera permission blocked',
  unavailable: 'No camera available',
};

const BODY = {
  starting: 'Allow camera access when your browser asks.',
  scanning: 'Hold steady — this connects your session to the station automatically.',
  denied: 'Allow camera access in your browser settings, then reload to scan the station code.',
  unavailable: 'This device has no camera the browser can reach.',
};

/** Live camera viewfinder that decodes the station QR code. */
export default function QrScanner({ station = 'Station 2', onScanned, onCancel }) {
  const { state, code, videoRef, canvasRef, skip } = useQrScanner({ onDecode: onScanned });

  const isScanning = state === 'starting' || state === 'scanning';
  const cameraFailed = state === 'denied' || state === 'unavailable';
  const body = state === 'found' ? (code ? `Station code · ${code}` : 'Starting your contactless scan…') : BODY[state];

  return (
    <Card className={styles.card}>
      <p className="label center tight">{station}</p>

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
        {HEADLINE[state]}
      </p>
      <p className="muted center">{body}</p>

      {cameraFailed && <Button onClick={skip}>Continue without camera</Button>}
      <Button variant="link" onClick={onCancel}>
        Cancel
      </Button>
    </Card>
  );
}
