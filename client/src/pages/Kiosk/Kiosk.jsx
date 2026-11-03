import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ScanFace, RefreshCw, Check, Loader } from 'lucide-react';
import { getStationCode, getStationLive } from '../../api';
import Layout from '../../components/Layout';
import { Card, Spinner, ErrorState } from '../../components/ui';
import styles from './Kiosk.module.css';

/** Fetch a fresh code this long before the current one expires, so the screen never shows a dead code. */
const REFRESH_EARLY_MS = 60 * 1000;

/**
 * The station's own screen: shows the signed QR code patients scan to start.
 * The code is made and signed by the server and expires, so a photo of it stops working.
 * `?station=station-2` picks the station.
 */
export default function Kiosk() {
  const [params] = useSearchParams();
  const stationId = params.get('station') || 'station-2';
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let timer;
    let active = true;

    async function load() {
      try {
        const next = await getStationCode(stationId);
        if (!active) return;
        setData(next);
        setError(null);
        const wait = new Date(next.expiresAt) - Date.now() - REFRESH_EARLY_MS;
        timer = setTimeout(load, Math.max(wait, 5000));
      } catch (err) {
        if (!active) return;
        setError(err.message);
        timer = setTimeout(load, 10000); // keep trying — a kiosk has nobody to press reload
      }
    }

    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [stationId]);

  const live = useStationLive(stationId);

  if (error && !data) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  return (
    <Layout eyebrow="Aura Screen kiosk" title={stationLabel(stationId)} showTabs={false}>
      <Card className={styles.card}>
        <p className="label center tight">Scan to begin</p>
        <img
          className={styles.qr}
          src={`data:image/svg+xml;utf8,${encodeURIComponent(data.svg)}`}
          alt={`QR code for ${stationLabel(stationId)}`}
        />
        <p className={styles.headline}>
          <ScanFace size={18} strokeWidth={1.7} aria-hidden="true" />
          Open the Aura Screen app and tap “Begin contactless scan”
        </p>
        <p className="muted center">Point your phone at this code. Other QR codes will not start a scan.</p>
        <p className="muted small icon-line center">
          <RefreshCw size={12} aria-hidden="true" /> This code changes every few minutes for your security.
        </p>
        <LiveStatus scan={live} />
      </Card>
    </Layout>
  );
}

const STAGE_TEXT = {
  linked: 'Phone linked — starting the capture',
  capturing: 'Capturing — please hold still',
  uploading: 'Sending the readings to the model',
  analysing: 'Model analysing the capture',
  done: 'Done — the results are on the phone',
  failed: 'The scan stopped — please scan again',
};

/** What the station is doing right now: idle, or the stage of the scan a phone started here. */
function LiveStatus({ scan }) {
  if (!scan) return <p className={styles.live}>Waiting for a patient to scan</p>;
  const started = scan.stages?.capturing && new Date(scan.stages.capturing).getTime();
  const left = scan.stage === 'capturing' && started ? Math.max(0, Math.ceil(scan.captureSeconds - (Date.now() - started) / 1000)) : null;
  const Icon = scan.stage === 'done' ? Check : scan.stage === 'failed' ? null : Loader;
  return (
    <p className={`${styles.live} ${styles[scan.stage] ?? ''}`.trim()} role="status">
      {Icon && <Icon size={16} aria-hidden="true" />}
      {STAGE_TEXT[scan.stage]}
      {left != null && ` · ${left} s`}
    </p>
  );
}

/** Polls the station's live status, so the kiosk follows a scan started from a phone. */
function useStationLive(stationId) {
  const [scan, setScan] = useState(null);
  useEffect(() => {
    let active = true;
    const tick = () => getStationLive(stationId).then((r) => active && setScan(r.scan), () => {});
    tick();
    const timer = setInterval(tick, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [stationId]);
  return scan;
}

/** "station-2" → "Station 2" */
function stationLabel(id) {
  return id.replace(/^station-/, 'Station ');
}
