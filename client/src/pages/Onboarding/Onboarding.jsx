import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Check } from 'lucide-react';
import useAuth from '../../hooks/useAuth';
import Layout from '../../components/Layout';
import { Card } from '../../components/ui';
import DetailsForm from './DetailsForm';
import PastReportsStep from './PastReportsStep';
import styles from './Onboarding.module.css';

const STEPS = [
  { key: 'account', label: 'Account' },
  { key: 'details', label: 'Your details' },
  { key: 'reports', label: 'Past reports' },
];

/** The two screens that stand between a fresh sign-in and the Scan Hub. */
export default function Onboarding() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(user?.profileComplete ? 'reports' : 'details');

  if (!user) return <Navigate to="/signin" replace />;

  const currentIndex = step === 'details' ? 1 : 2;

  return (
    <Layout eyebrow="Aura Screen" title="Set up your record" showTabs={false}>
      <Card className={styles.progress}>
        <ol className={styles.steps}>
          {STEPS.map((entry, index) => (
            <li
              key={entry.key}
              className={`${styles.step} ${index === currentIndex ? styles.stepCurrent : ''} ${
                index < currentIndex ? styles.stepDone : ''
              }`.trim()}
            >
              <span className={styles.stepMark} aria-hidden="true">
                {index < currentIndex ? <Check size={13} strokeWidth={2.4} /> : index + 1}
              </span>
              {entry.label}
            </li>
          ))}
        </ol>
      </Card>

      {step === 'details' ? (
        <DetailsForm user={user} onSaved={() => setStep('reports')} />
      ) : (
        <PastReportsStep
          user={user}
          onBack={() => setStep('details')}
          onFinish={() => navigate('/', { replace: true })}
        />
      )}
    </Layout>
  );
}
