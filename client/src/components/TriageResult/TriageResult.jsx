import { useState } from 'react';
import { Database, Scale, MessageCircleQuestion, PhoneCall, Info, RotateCcw } from 'lucide-react';
import { askTriage } from '../../api';
import { Card, Button, StatTile } from '../ui';
import styles from './TriageResult.module.css';

const TONE = {
  URGENT: 'crit',
  SEE_DOCTOR_SOON: 'warn',
  SELF_CARE: 'ok',
  RETAKE: 'quiet',
  REMEASURE: 'quiet',
  NOT_SUITABLE: 'quiet',
};
const LEVEL_WORDS = {
  URGENT: 'Urgent',
  SEE_DOCTOR_SOON: 'See a doctor soon',
  SELF_CARE: 'Self-care',
  RETAKE: 'Retake',
  NOT_SUITABLE: 'Not suitable',
};
const READING_TONE = { in: 'ok', borderline: 'warn', out: 'crit' };

const fmt = (key, v) => (v == null ? '—' : key === 'temperature' ? v.toFixed(1) : Math.round(v));

/** One reasoning-model result: the level, the data it came from, every reading, the reasons and follow-up Q&A. */
export default function TriageResult({ result, onAgain }) {
  const { sample, card } = result;
  const ref = sample.reference_level;

  return (
    <div className="stack">
      <div className={`${styles.banner} ${styles[TONE[result.level]]}`}>
        <p className={styles.bannerLabel}>{result.label}</p>
        <p className={styles.bannerAdvice}>{card.advice}</p>
      </div>

      {card.contacts.length > 0 && (
        <Card className={styles.contacts}>
          <PhoneCall size={18} strokeWidth={1.8} aria-hidden="true" />
          <div>
            {card.contacts.map((c) => (
              <p key={c.number}>
                {c.name}: <strong>{c.number}</strong>
              </p>
            ))}
            {!card.contacts_verified && <p className="muted small">Numbers not yet verified by the team.</p>}
          </div>
        </Card>
      )}

      <Card>
        <p className="label icon-line">
          <Database size={13} aria-hidden="true" /> Demo data from the QR code
        </p>
        <h3 className={styles.sampleTitle}>{sample.title}</h3>
        <p className="muted small">{sample.dataset}</p>
        <p className="muted">{sample.note}</p>
        {sample.camera_reference && (
          <p className="muted small">
            Camera {sample.camera_reference.camera_bpm} bpm · contact sensor {sample.camera_reference.sensor_bpm} bpm
          </p>
        )}
        {ref && (
          <p className={`${styles.reference} ${result.reference_match ? styles.match : styles.differ}`}>
            <Scale size={14} aria-hidden="true" /> Emergency-department reference: <strong>{LEVEL_WORDS[ref]}</strong>
            {result.reference_match ? ' · the rules agree' : ' · the rules decided differently'}
          </p>
        )}
        <p className="muted small">Temporary sample file, not a live reading. Source: {sample.source}.</p>
      </Card>

      <Card>
        <p className="label">Readings</p>
        <div className={styles.readings}>
          {result.readings.map((r) => (
            <StatTile key={r.key} className={styles.reading}>
              <StatTile.Label>{r.measure}</StatTile.Label>
              <StatTile.Value>
                {fmt(r.key, r.value)} <span className={styles.unit}>{r.value == null ? '' : r.unit}</span>
              </StatTile.Value>
              <p className={`${styles.readingStatus} ${styles[READING_TONE[r.status] || 'quiet']}`}>{r.status_text}</p>
              {r.normal && <p className="muted small">usual {r.normal}</p>}
              {r.readings.length > 1 && (
                <p className="muted small">readings {r.readings.map((x) => fmt(r.key, x)).join(' / ')}</p>
              )}
            </StatTile>
          ))}
        </div>
        {result.answers.length > 0 && (
          <p className="muted small">
            Answers: {result.answers.map((a) => `${a.item}: ${a.answer}`).join(' · ')}
          </p>
        )}
      </Card>

      <Card>
        <p className="label">Why</p>
        <p className={styles.summary}>{card.summary}</p>
        <ul className={styles.reasons}>
          {card.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {card.uncertainty && <p className="muted">Uncertain: {card.uncertainty}</p>}
        {card.next_step && <p className="muted">Next step: {card.next_step}</p>}
        <p className={`muted small icon-line ${styles.rule}`}>
          <Info size={12} aria-hidden="true" />
          Rule {result.rule.id} decided
          {result.remeasured ? ` after one rest-and-remeasure round (${result.first_rule})` : ''}. Text:{' '}
          {result.text_source.startsWith('llm') ? 'local language model, checked by the verifier' : 'fixed template'}.
        </p>
      </Card>

      <FollowUp runId={result.run_id} />

      <p className="muted small center">
        {card.disclaimer} Rules {result.rules_version} are a draft, not yet reviewed by a clinician.
      </p>
      {onAgain && (
        <Button variant="link" onClick={onAgain}>
          <RotateCcw size={14} aria-hidden="true" /> Scan another code
        </Button>
      )}
    </div>
  );
}

function FollowUp({ runId }) {
  const [question, setQuestion] = useState('');
  const [chat, setChat] = useState([]);
  const [busy, setBusy] = useState(false);

  async function ask(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    try {
      const res = await askTriage(runId, q);
      setChat((c) => [...c, { q, a: res.answer }]);
      setQuestion('');
    } catch (err) {
      setChat((c) => [...c, { q, a: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <p className="label icon-line">
        <MessageCircleQuestion size={13} aria-hidden="true" /> Ask about this result
      </p>
      {chat.map((m, i) => (
        <div key={i} className={styles.qa}>
          <p className={styles.q}>{m.q}</p>
          <p>{m.a}</p>
        </div>
      ))}
      <form className={styles.ask} onSubmit={ask}>
        <input
          className={styles.input}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. why was my heart rate measured twice?"
          aria-label="Your question"
        />
        <Button type="submit" disabled={busy} className={styles.askButton}>
          {busy ? '…' : 'Ask'}
        </Button>
      </form>
      <p className="muted small">Answers come only from this result and approved text: no medicines or diagnoses.</p>
    </Card>
  );
}
