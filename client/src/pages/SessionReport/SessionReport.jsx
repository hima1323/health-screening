import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Stethoscope, Clock, ShieldCheck, ArrowRight, Copy, Check, Share2, Brain, QrCode } from 'lucide-react';
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
import { rangePosition } from '../../utils/range';
import { RESULTS } from '../../utils/results';
import TriageResult from '../../components/TriageResult';
import { modelCall } from '../../utils/reasoning';
import styles from './SessionReport.module.css';
import usePrefs from '../../hooks/usePrefs';

/** "Normal is 72–96 bpm — yours is above it." Falls back to the range alone if it can't be read. */
function rangeLine({ value, normalRange }, unit) {
  if (!normalRange) return '';
  const range = rangePosition(value, normalRange);
  if (!range) return `Normal is ${normalRange}.`;
  const where = { above: 'above it', below: 'below it', within: 'within it' }[range.position];
  return `Normal is ${range.low}–${range.high} ${unit} — yours is ${where}.`;
}

/** The model's reading in a patient's words — the doctor's side has the full analysis. */
const MODEL_READING = {
  low: {
    title: 'Low mental load',
    text: 'Your signals looked like someone at ease — no sign of high mental load or stress during the capture.',
  },
  high: {
    title: 'High mental load',
    text: 'Your signals looked like someone working hard mentally — concentration, stress or strain. This is how your body responded during the capture, not a diagnosis.',
  },
  unsure: {
    title: 'No clear reading',
    text: 'The signals were not clear enough for the model to say either way.',
  },
};

/** The results of a completed screening session. */
export default function SessionReport() {
  const { sessionId } = usePrimary();
  return sessionId ? <Report sessionId={sessionId} /> : <NoReport />;
}

function NoReport() {
  const { t } = usePrefs();
  const navigate = useNavigate();
  return (
    <Layout eyebrow="Biometric screening" title="Your results">
      <Card className={styles.empty}>
        <IconBadge tone="rose">
          <QrCode size={18} strokeWidth={1.6} />
        </IconBadge>
        <h3>{t('No results yet')}</h3>
        <p className="muted center">{t('Scan the QR code on a station to take your first reading. Your results appear here.')}</p>
        <Button onClick={() => navigate('/')}>{t('Go to Scan Hub')}</Button>
      </Card>
    </Layout>
  );
}

function Report({ sessionId }) {
  const { t } = usePrefs();
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
              <h3>{t('Nurse check requested')}</h3>
            </CardHeading>
            <StatusPill dot={false}>{`Queue #${nurseCheck.queueId}`}</StatusPill>
          </CardRow>
          <p className="muted">{t(nurseCheck.message)}</p>
          <p className="muted small icon-line">
            <Clock size={13} aria-hidden="true" /> {t('Estimated review')} · {t(nurseCheck.reviewTime)} · {t(nurseCheck.room)}
          </p>
        </Card>
      )}

      <Card className={styles.results}>
        <h3>{t('Key results')}</h3>
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
                    <span className={styles.resultName}>{t(label)}</span>
                  </CardHeading>
                  <StatusPill dot={false}>{result.status}</StatusPill>
                </CardRow>
                <p className={styles.bigStat}>
                  {result.value}
                  <span className={styles.unit}> {unit}</span>
                </p>
                <p className={styles.plain}>
                  {t(measures)} {t(rangeLine(result, unit))} {t(result.note)}
                </p>
              </li>
            );
          })}
        </ul>
      </Card>

      {data.reasoning && <TriageResult result={data.reasoning} source="Demo case the station sent" />}
      {!data.reasoning && data.model && <ModelReading model={data.model} />}

      <Button onClick={() => setSharing(true)} aria-haspopup="dialog">
        {t(`Share with doctor · Code ${shareCode}`)}
        <ArrowRight size={15} aria-hidden="true" />
      </Button>
      <p className="muted small icon-line center">
        <ShieldCheck size={13} aria-hidden="true" /> {t(encryptionNote)}
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

function ModelReading({ model }) {
  const { t } = usePrefs();
  const { summary, sample, skinTempC } = model;
  const reading = MODEL_READING[summary.abstain ? 'unsure' : summary.label];
  const sure = Math.round(summary.confidence * 100);
  return (
    <Card className={styles.model}>
      <CardRow>
        <CardHeading>
          <IconBadge tone={summary.label === 'high' && !summary.abstain ? 'amber' : undefined}>
            <Brain size={17} strokeWidth={1.7} />
          </IconBadge>
          <h3>{t('What the model read')}</h3>
        </CardHeading>
        <StatusPill dot={false}>{reading.title}</StatusPill>
      </CardRow>
      <p className={styles.plain}>{t(reading.text)}</p>
      {!summary.abstain && (
        <div className={styles.meter} role="img" aria-label={t(`The model is ${sure}% sure`)}>
          <span style={{ width: `${sure}%` }} />
          <p className="muted small">{t(`The model is ${sure}% sure`)}</p>
        </div>
      )}
      {skinTempC != null && (
        <p className="muted small">{t(`Finger skin temperature ${skinTempC.toFixed(1)} °C — skin runs cooler than the body inside.`)}</p>
      )}
      <p className="muted small">
        {t(`Demo station: it replayed a recorded ${sample.task} from a research study instead of live sensors.`)}
      </p>
    </Card>
  );
}

/** The message a patient sends: the session, each key result against its range, and the code. */
function shareText(data, sessionId) {
  const lines = RESULTS.filter(({ key }) => data[key]).map(({ key, label, unit }) => {
    const r = data[key];
    return `• ${label}: ${r.value} ${unit} — ${r.status}${r.normalRange ? ` (normal ${r.normalRange})` : ''}`;
  });
  const call = modelCall(data);
  if (call) lines.push(`• Reasoning model: ${call.title}`);
  return [
    `My Aura Screen results, session ${sessionId}:`,
    ...lines,
    '',
    `Share code: ${data.shareCode} — enter it in Aura Screen to open the full report.`,
  ].join('\n');
}

/** Hands the share code to the doctor: copy it, or send it with the results through the phone's share menu. */
function ShareSheet({ shareCode, text, onClose }) {
  const { t } = usePrefs();
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
      <p>{t('Give your doctor this code. They enter it in Aura Screen to open your full report.')}</p>
      <p className={styles.shareCode} aria-label={`Share code ${shareCode.split('').join(' ')}`}>
        {shareCode}
      </p>
      <div className={styles.shareActions}>
        <Button onClick={copy}>
          {copied === 'ok' ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {t(copied === 'ok' ? 'Code copied' : 'Copy code')}
        </Button>
        {canShare && (
          <Button variant="link" onClick={share}>
            <Share2 size={15} aria-hidden="true" /> {t('Send code and results…')}
          </Button>
        )}
      </div>
      <p className="muted small center" role="status">
        {t(copied === 'failed' ? 'Could not copy — please write the code down.' : 'The code only opens this report.')}
      </p>
    </Sheet>
  );
}
