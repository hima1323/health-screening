import { useState } from 'react';
import { Stethoscope, Clock, HeartPulse, Thermometer, Wind, ShieldCheck, ArrowRight, Copy, Check, Share2 } from 'lucide-react';
import { getReport } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import { Sheet } from '../../components/InfoSheet';
import {
  Card,
  CardRow,
  CardHeading,
  Button,
  StatusPill,
  IconBadge,
  Spinner,
  ErrorState,
} from '../../components/ui';
import styles from './SessionReport.module.css';

/** The key results, in the order a patient reads them, with what each one measures. */
const RESULTS = [
  { key: 'heartRate', label: 'Heart rate', unit: 'bpm', icon: HeartPulse, tone: 'rose', measures: 'How many times your heart beats in a minute.' },
  { key: 'bodyTemp', label: 'Body temperature', unit: '°C', icon: Thermometer, tone: 'amber', measures: 'How warm your body is inside.' },
  { key: 'respiration', label: 'Breathing rate', unit: '/min', icon: Wind, tone: undefined, measures: 'How many breaths you take in a minute.' },
];

/** "Normal is 72–96 bpm — yours is above it." Falls back to the range alone if it can't be read. */
function rangeLine({ value, normalRange }, unit) {
  if (!normalRange) return '';
  const match = normalRange.match(/([\d.]+)\s*[–-]\s*([\d.]+)/);
  if (!match) return `Normal is ${normalRange}.`;
  const [low, high] = [Number(match[1]), Number(match[2])];
  const where = value > high ? 'above it' : value < low ? 'below it' : 'within it';
  return `Normal is ${low}–${high} ${unit} — yours is ${where}.`;
}

/** The results of a completed screening session. */
export default function SessionReport() {
  const { sessionId } = usePrimary();
  const { data, error } = useResource(() => getReport(sessionId), [sessionId]);
  const [sharing, setSharing] = useState(false);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { nurseCheck, shareCode, encryptionNote } = data;

  return (
    <Layout eyebrow="Biometric screening" title="Your results">
      {nurseCheck && (
        <Card accent="rose" className={styles.alert}>
          <CardRow>
            <CardHeading>
              <IconBadge tone="rose">
                <Stethoscope size={17} strokeWidth={1.7} />
              </IconBadge>
              <h3>Nurse check requested</h3>
            </CardHeading>
            <StatusPill dot={false}>{`Queue #${nurseCheck.queueId}`}</StatusPill>
          </CardRow>
          <p className="muted">{nurseCheck.message}</p>
          <p className="muted small icon-line">
            <Clock size={13} aria-hidden="true" /> Estimated review · {nurseCheck.reviewTime} · {nurseCheck.room}
          </p>
        </Card>
      )}

      <Card className={styles.results}>
        <h3>Key results</h3>
        <ul className={styles.resultList}>
          {RESULTS.map(({ key, label, unit, icon: Icon, tone, measures }) => {
            const result = data[key];
            if (!result) return null;
            return (
              <li key={key} className={styles.result}>
                <CardRow>
                  <CardHeading>
                    <IconBadge tone={tone}>
                      <Icon size={17} strokeWidth={1.7} />
                    </IconBadge>
                    <span className={styles.resultName}>{label}</span>
                  </CardHeading>
                  <StatusPill dot={false}>{result.status}</StatusPill>
                </CardRow>
                <p className={styles.bigStat}>
                  {result.value}
                  <span className={styles.unit}> {unit}</span>
                </p>
                <p className={styles.plain}>
                  {measures} {rangeLine(result, unit)} {result.note}
                </p>
              </li>
            );
          })}
        </ul>
      </Card>

      <Button onClick={() => setSharing(true)} aria-haspopup="dialog">
        Share with doctor · Code {shareCode}
        <ArrowRight size={15} aria-hidden="true" />
      </Button>
      <p className="muted small icon-line center">
        <ShieldCheck size={13} aria-hidden="true" /> {encryptionNote}
      </p>

      {sharing && (
        <ShareSheet
          shareCode={shareCode}
          text={shareText(data, sessionId)}
          onClose={() => setSharing(false)}
        />
      )}
    </Layout>
  );
}

/** The message a patient sends: the session, each key result against its range, and the code. */
function shareText(data, sessionId) {
  const lines = RESULTS.filter(({ key }) => data[key]).map(({ key, label, unit }) => {
    const r = data[key];
    return `• ${label}: ${r.value} ${unit} — ${r.status}${r.normalRange ? ` (normal ${r.normalRange})` : ''}`;
  });
  return [
    `My Aura Screen results, session ${sessionId}:`,
    ...lines,
    '',
    `Share code: ${data.shareCode} — enter it in Aura Screen to open the full report.`,
  ].join('\n');
}

/** Hands the share code to the doctor: copy it, or send it with the results through the phone's share menu. */
function ShareSheet({ shareCode, text, onClose }) {
  const [copied, setCopied] = useState(null); // null | 'ok' | 'failed'
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';

  async function copy() {
    try {
      await navigator.clipboard.writeText(shareCode);
      setCopied('ok');
    } catch {
      setCopied('failed');
    }
    setTimeout(() => setCopied(null), 2500);
  }

  async function share() {
    try {
      await navigator.share({ title: 'My Aura Screen results', text });
    } catch {
      /* the patient closed the share menu — nothing to do */
    }
  }

  return (
    <Sheet title="Share with your doctor" onClose={onClose}>
      <p>Give your doctor this code. They enter it in Aura Screen to open your full report.</p>
      <p className={styles.shareCode} aria-label={`Share code ${shareCode.split('').join(' ')}`}>
        {shareCode}
      </p>
      <div className={styles.shareActions}>
        <Button onClick={copy}>
          {copied === 'ok' ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {copied === 'ok' ? 'Code copied' : 'Copy code'}
        </Button>
        {canShare && (
          <Button variant="link" onClick={share}>
            <Share2 size={15} aria-hidden="true" /> Send code and results…
          </Button>
        )}
      </div>
      <p className="muted small center" role="status">
        {copied === 'failed' ? 'Could not copy — please write the code down.' : 'The code only opens this report.'}
      </p>
    </Sheet>
  );
}
