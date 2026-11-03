import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ScanFace, Shuffle, Database, Timer } from 'lucide-react';
import { getTriageCode, getTriageSamples } from '../../api';
import Layout from '../../components/Layout';
import { Card, Button, Spinner, ErrorState } from '../../components/ui';
import styles from './Kiosk.module.css';

const REFRESH_EARLY_MS = 60 * 1000;

/**
 * Reasoning-model demo kiosk (/kiosk?demo=1): pick a sample data file from the past datasets, and the screen shows a
 * signed, temporary QR code that carries it. A phone on /demo scans it and the reasoning model runs on that sample.
 * No database needed.
 */
export default function DemoKiosk() {
  const [params] = useSearchParams();
  const stationId = params.get('station') || 'station-2';
  const [samples, setSamples] = useState(null);
  const [sample, setSample] = useState(params.get('sample') || '');
  const [code, setCode] = useState(null);
  const [error, setError] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    getTriageSamples().then(
      (list) => {
        setSamples(list);
        setSample((s) => s || list[0]?.id || '');
      },
      (err) => setError(err.message)
    );
  }, []);

  useEffect(() => {
    if (!sample) return undefined;
    let timer;
    let active = true;
    async function load() {
      try {
        const next = await getTriageCode(stationId, sample);
        if (!active) return;
        setCode(next);
        setError(null);
        timer = setTimeout(load, Math.max(new Date(next.expiresAt) - Date.now() - REFRESH_EARLY_MS, 5000));
      } catch (err) {
        if (!active) return;
        setError(err.message);
        timer = setTimeout(load, 10000);
      }
    }
    setCode(null);
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [stationId, sample]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const current = useMemo(() => samples?.find((s) => s.id === sample), [samples, sample]);
  const groups = useMemo(
    () => (samples || []).reduce((acc, s) => ({ ...acc, [s.dataset]: [...(acc[s.dataset] || []), s] }), {}),
    [samples]
  );

  if (error && !samples) return <ErrorState message={error} />;
  if (!samples) return <Spinner />;

  const shuffle = () => {
    const others = samples.filter((s) => s.id !== sample);
    setSample(others[Math.floor(Math.random() * others.length)].id);
  };
  const left = code ? Math.max(0, Math.round((new Date(code.expiresAt) - now) / 1000)) : null;

  return (
    <Layout eyebrow="Aura Screen kiosk · reasoning model demo" title="Scan to begin" showTabs={false}>
      <Card className={styles.card}>
        <div className={styles.demoPicker}>
          <label className="label" htmlFor="demo-sample">
            Demo sample data
          </label>
          <select id="demo-sample" className={styles.select} value={sample} onChange={(e) => setSample(e.target.value)}>
            {Object.entries(groups).map(([dataset, items]) => (
              <optgroup key={dataset} label={dataset}>
                {items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <Button variant="link" onClick={shuffle}>
            <Shuffle size={14} aria-hidden="true" /> Random sample
          </Button>
        </div>

        {code ? (
          <img
            className={styles.qr}
            src={`data:image/svg+xml;utf8,${encodeURIComponent(code.svg)}`}
            alt="Demo QR code carrying the selected sample"
          />
        ) : (
          <Spinner />
        )}

        {current && (
          <p className="muted small icon-line center">
            <Database size={12} aria-hidden="true" /> {current.dataset}: {current.note}
          </p>
        )}
        <p className={styles.headline}>
          <ScanFace size={18} strokeWidth={1.7} aria-hidden="true" />
          Open Aura Screen at /demo on your phone and scan this code
        </p>
        {left !== null && (
          <p className="muted small icon-line center">
            <Timer size={12} aria-hidden="true" /> Temporary code: expires in {Math.floor(left / 60)}:
            {String(left % 60).padStart(2, '0')}, then a new one appears. Sample data only, draft rules.
          </p>
        )}
        {error && <p className="muted small">{error}</p>}
      </Card>
    </Layout>
  );
}
