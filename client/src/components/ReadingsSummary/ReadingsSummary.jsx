import { CircleCheck, CircleAlert, CircleHelp } from 'lucide-react';
import styles from './ReadingsSummary.module.css';

/** What each reading tells you, in one line; shown in the detailed version. */
const MEANING = {
  'Heart rate at rest': 'How many times your heart beats in a minute while you sit still.',
  'Heart rate after exercise': 'How fast your heart beats right after moving — it should go up.',
  'Heart rate while driving': 'How fast your heart beat in traffic; stress raises it for a while.',
  'Heart-rate variability':
    'How much the gap between heartbeats changes. More change usually means a relaxed, healthy heart.',
  'Breathing rate at rest': 'How many breaths you take in a minute while sitting still.',
  'Body temperature': 'Your core temperature, measured by the thermal camera at the corner of the eye.',
  'Forehead temperature': 'The skin temperature of your forehead, from the thermal camera.',
  'Mouth temperature while drinking': 'How much a cold drink cooled the skin around your mouth.',
  "Body's response to harder tasks":
    'In how many rounds your body reacted the way the task asked: calm in easy rounds, working harder in hard ones.',
};

/** The normal band of "50–100", "20 or more" or "below 38.0" as { low, high }; null when it isn't numeric. */
function band(normal) {
  const between = normal.match(/^([\d.]+)\s*–\s*([\d.]+)/);
  if (between) return { low: +between[1], high: +between[2] };
  const atLeast = normal.match(/^([\d.]+) or more/);
  if (atLeast) return { low: +atLeast[1], high: null };
  const below = normal.match(/^below ([\d.]+)/);
  if (below) return { low: null, high: +below[1] };
  return null;
}

/** Where the reading sits: a track with the normal band shaded and a marker at the value. */
function RangeBar({ value, normal, ok }) {
  const b = band(normal);
  if (!b) return null;
  const lo = b.low ?? b.high * 0.9;
  const hi = b.high ?? b.low * 2;
  const pad = (hi - lo) * 0.4;
  const min = Math.min(lo - pad, value);
  const max = Math.max(hi + pad, value);
  const at = (x) => `${((x - min) / (max - min)) * 100}%`;
  return (
    <div className={styles.bar} aria-hidden="true">
      <span
        className={styles.band}
        style={{ left: b.low == null ? 0 : at(b.low), right: b.high == null ? 0 : `calc(100% - ${at(b.high)})` }}
      />
      <span className={`${styles.marker} ${ok ? styles.markerFine : styles.markerCheck}`} style={{ left: at(value) }} />
    </div>
  );
}

const STATUS = {
  normal: { title: 'Normal', Icon: CircleCheck },
  abnormal: { title: 'Not normal', Icon: CircleAlert },
  unclear: { title: 'No health reading', Icon: CircleHelp },
};

/**
 * The patient's whole result: normal or not, then each reading, its normal range, and whether it is fine.
 * `detailed` adds what each reading means and a bar showing where it sits against the normal range.
 */
export default function ReadingsSummary({ summary, advice, detailed = false }) {
  const { title, Icon } = STATUS[summary.status] ?? STATUS.unclear;

  return (
    <div className={styles.summary}>
      <div className={`${styles.verdict} ${styles[summary.status]}`}>
        <Icon size={28} strokeWidth={1.7} aria-hidden="true" />
        <div>
          <p className={styles.title}>{title}</p>
          <p className={styles.text}>{summary.text}</p>
        </div>
      </div>

      <ul className={styles.readings}>
        {summary.readings.map((r) => (
          <li key={r.label} className={styles.reading}>
            <div className={styles.what}>
              <p className={styles.label}>{r.label}</p>
              <p className={styles.range}>Normal: {r.normal}</p>
              {r.note && <p className={styles.range}>{r.note}</p>}
            </div>
            <p className={styles.value}>
              {r.value} <small>{r.unit}</small>
            </p>
            <span className={`${styles.badge} ${r.ok ? styles.fine : styles.check}`}>{r.ok ? 'Fine' : 'Check'}</span>
            {detailed && (
              <div className={styles.detail}>
                <RangeBar value={r.value} normal={r.normal} ok={r.ok} />
                {MEANING[r.label] && <p className={styles.meaning}>{MEANING[r.label]}</p>}
              </div>
            )}
          </li>
        ))}
      </ul>

      {advice && (
        <p className={styles.advice}>
          <strong>See a doctor? {advice.answer}.</strong> {advice.text}
        </p>
      )}
    </div>
  );
}
