import { useNavigate } from 'react-router-dom';
import { ArrowRight, HeartPulse, Thermometer, Video } from 'lucide-react';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import { Button, Card } from '../../components/ui';
import styles from './Welcome.module.css';

const POINTS = [
  { icon: Video, text: 'A camera reads the pulse in your skin' },
  { icon: Thermometer, text: 'A thermal sensor takes your temperature' },
  { icon: HeartPulse, text: 'An ECG pad steps in only if a reading needs confirming' },
];

/** The introduction a first-time patient reads: one screen, one way on. */
export default function Welcome() {
  const navigate = useNavigate();

  return (
    <Layout eyebrow="Aura Screen" title="Welcome" showTabs={false} showPrefs={false}>
      <Card className={styles.intro}>
        <AuraOrb size={180} value={72} caption="bpm · sample read" />

        <h2 className={styles.title}>A screening you never have to touch</h2>
        <p className={styles.body}>
          Stand at the station, hold still for ninety seconds, and your vitals are read from across the room — no cuff,
          no probe, no needle.
        </p>

        <ul className={styles.points}>
          {POINTS.map((point) => (
            <li key={point.text}>
              <point.icon size={17} strokeWidth={1.6} aria-hidden="true" />
              {point.text}
            </li>
          ))}
        </ul>

        {/* the main page needs an account, so a guest passes through sign-in on the way */}
        <Button className={styles.start} onClick={() => navigate('/signin')}>
          Get started
          <ArrowRight size={15} aria-hidden="true" />
        </Button>
      </Card>
    </Layout>
  );
}
