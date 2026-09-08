import { Stethoscope, Clock, Thermometer, Wind, ShieldCheck, ArrowRight } from 'lucide-react';
import { getReport } from '../../api';
import usePrimary from '../../hooks/usePrimary';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import AuraOrb from '../../components/AuraOrb';
import {
  Card,
  CardRow,
  CardHeading,
  Button,
  StatTile,
  StatusPill,
  IconBadge,
  Spinner,
  ErrorState,
} from '../../components/ui';
import styles from './SessionReport.module.css';

/** The results of a completed screening session. */
export default function SessionReport() {
  const { sessionId } = usePrimary();
  const { data, error } = useResource(() => getReport(sessionId), [sessionId]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Spinner />;

  const { nurseCheck, heartRate, bodyTemp, respiration, shareCode, encryptionNote } = data;

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

      <Card accent="amber">
        <CardRow>
          <h3>Heart rate</h3>
          <StatusPill dot={false}>{heartRate.status}</StatusPill>
        </CardRow>

        <div className={styles.heartLayout}>
          <AuraOrb size={172} value={heartRate.value} caption="bpm">
            <svg viewBox="0 0 100 24" className={styles.ecg} aria-hidden="true">
              <path
                d="M0 12 H26 L33 3 L41 21 L49 8 L56 16 L62 12 H100"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </AuraOrb>

          <div className={styles.heartStats}>
            <StatTile.Row>
              <StatTile className={styles.centeredTile}>
                <StatTile.Value>{heartRate.resting}</StatTile.Value>
                <StatTile.Label>Resting</StatTile.Label>
              </StatTile>
              <StatTile className={styles.centeredTile}>
                <StatTile.Value>{heartRate.peak}</StatTile.Value>
                <StatTile.Label>Peak</StatTile.Label>
              </StatTile>
              <StatTile className={styles.centeredTile}>
                <StatTile.Value accent>{heartRate.variability}</StatTile.Value>
                <StatTile.Label>Variability</StatTile.Label>
              </StatTile>
            </StatTile.Row>
            <p className="muted">{heartRate.note}</p>
          </div>
        </div>
      </Card>

      <div className="grid-two">
        <Card accent="amber">
          <CardRow>
            <IconBadge tone="amber">
              <Thermometer size={17} strokeWidth={1.7} />
            </IconBadge>
            <StatusPill dot={false}>{bodyTemp.status}</StatusPill>
          </CardRow>
          <p className={styles.bigStat}>
            {bodyTemp.value}
            <span className={styles.unit}> °C</span>
          </p>
          <p className={`label ${styles.statLabel}`}>Body temp</p>
          <p className="muted">{bodyTemp.note}</p>
        </Card>

        <Card accent="sage">
          <CardRow>
            <IconBadge>
              <Wind size={17} strokeWidth={1.7} />
            </IconBadge>
            <StatusPill dot={false}>{respiration.status}</StatusPill>
          </CardRow>
          <p className={styles.bigStat}>
            {respiration.value}
            <span className={styles.unit}> /min</span>
          </p>
          <p className={`label ${styles.statLabel}`}>Respiration</p>
          <p className="muted">{respiration.note}</p>
        </Card>
      </div>

      <Button>
        Share with doctor · Code {shareCode}
        <ArrowRight size={15} aria-hidden="true" />
      </Button>
      <p className="muted small icon-line center">
        <ShieldCheck size={13} aria-hidden="true" /> {encryptionNote}
      </p>
    </Layout>
  );
}
