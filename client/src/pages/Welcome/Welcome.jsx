import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ScanFace, ShieldCheck, Sparkles, Video, Thermometer, HeartPulse } from 'lucide-react';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import { Button, Card, IconBadge } from '../../components/ui';
import styles from './Welcome.module.css';

/** The introduction a first-time patient reads before signing in. */
const SLIDES = [
  {
    key: 'contactless',
    icon: ScanFace,
    eyebrow: 'What this is',
    title: 'A screening you never have to touch',
    body: 'Aura Screen reads your vitals from across the room. Stand at the station, hold still for ninety seconds, and the capture is done — no cuff, no probe, no needle.',
    points: [
      { icon: Video, text: 'A camera reads the pulse in your skin' },
      { icon: Thermometer, text: 'A thermal sensor takes your temperature' },
      { icon: HeartPulse, text: 'An ECG pad steps in only if a reading needs confirming' },
    ],
  },
  {
    key: 'aura',
    icon: Sparkles,
    eyebrow: 'What you get',
    title: 'Every reading, gathered into one aura',
    body: 'Pulse, temperature and breathing settle into a single living orb. Tap it, tilt it, and watch the reading you have just given — then open the full report whenever you want the numbers.',
    orb: true,
  },
  {
    key: 'records',
    icon: ShieldCheck,
    eyebrow: 'What we ask',
    title: 'Your records stay yours',
    body: 'You create one account here, tell us a little about your health, and bring along any reports from earlier visits. Nothing is shared with a clinician until you hand over the share code.',
    points: [
      { icon: ShieldCheck, text: 'Consent is recorded before a single sensor starts' },
      { icon: ScanFace, text: 'Captures are processed on the station, not stored as video' },
    ],
  },
];

export default function Welcome() {
  const navigate = useNavigate();
  const [index, setIndex] = useState(0);

  const slide = SLIDES[index];
  const isLast = index === SLIDES.length - 1;
  const Icon = slide.icon;

  const advance = () => (isLast ? navigate('/signin') : setIndex((step) => step + 1));

  return (
    <Layout eyebrow="Aura Screen" title="Welcome" showTabs={false}>
      <div className={styles.intro}>
        <Card className={styles.copy}>
          <div className={styles.heading}>
            <IconBadge tone="rose">
              <Icon size={18} strokeWidth={1.6} />
            </IconBadge>
            <p className="label tight">{slide.eyebrow}</p>
          </div>

          <h2 className={styles.title}>{slide.title}</h2>
          <p className={styles.body}>{slide.body}</p>

          {slide.points && (
            <ul className={styles.points}>
              {slide.points.map((point) => (
                <li key={point.text}>
                  <point.icon size={17} strokeWidth={1.6} aria-hidden="true" />
                  {point.text}
                </li>
              ))}
            </ul>
          )}

          <div className={styles.dots} role="tablist" aria-label="Introduction steps">
            {SLIDES.map((entry, step) => (
              <button
                key={entry.key}
                type="button"
                role="tab"
                aria-selected={step === index}
                aria-label={entry.title}
                className={`${styles.dot} ${step === index ? styles.dotActive : ''}`.trim()}
                onClick={() => setIndex(step)}
              />
            ))}
          </div>

          <div className={styles.actions}>
            <Button variant="link" onClick={() => setIndex((step) => step - 1)} disabled={index === 0}>
              <ArrowLeft size={15} aria-hidden="true" /> Back
            </Button>
            <Button className={styles.next} onClick={advance}>
              {isLast ? 'Sign in to begin' : 'Next'}
              <ArrowRight size={15} aria-hidden="true" />
            </Button>
          </div>
        </Card>

        <Card className={styles.visual}>
          <AuraOrb
            size={200}
            value={slide.orb ? 72 : index + 1}
            caption={slide.orb ? 'bpm · sample read' : `of ${SLIDES.length}`}
          />
          <p className={styles.visualNote}>
            {slide.orb
              ? 'Move your pointer across the orb — it tilts with you.'
              : 'This is the orb your own reading will fill.'}
          </p>
          <Button variant="link" onClick={() => navigate('/signin')}>
            Skip the introduction
          </Button>
        </Card>
      </div>
    </Layout>
  );
}
