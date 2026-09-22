import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, KeyRound, Lock } from 'lucide-react';
import { getProviders } from '../../api';
import useAuth from '../../hooks/useAuth';
import useResource from '../../hooks/useResource';
import Layout from '../../components/Layout';
import GoogleButton from '../../components/GoogleButton';
import { Button, Card, IconBadge } from '../../components/ui';
import CredentialsForm from './CredentialsForm';
import styles from './SignIn.module.css';

const MODES = {
  register: { tab: 'Create account', title: 'Set up your Aura Screen account' },
  login: { tab: 'Sign in', title: 'Welcome back' },
};

/** Create an account or sign in, then carry on to onboarding. */
export default function SignIn() {
  const navigate = useNavigate();
  const { signIn, createAccount, signInWithGoogleCredential } = useAuth();
  const { data: providers } = useResource(getProviders, []);

  // a failed Google round trip comes back as ?error=
  const [params] = useSearchParams();

  const [mode, setMode] = useState('register');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(params.get('error'));

  const withGoogle = async (credential) => {
    setBusy(true);
    setError(null);
    try {
      const user = await signInWithGoogleCredential(credential);
      navigate(user.profileComplete ? '/' : '/onboarding', { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const submit = async (credentials) => {
    setBusy(true);
    setError(null);
    try {
      const user = mode === 'register' ? await createAccount(credentials) : await signIn(credentials);
      navigate(user.profileComplete ? '/' : '/onboarding', { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const switchTo = (next) => {
    setMode(next);
    setError(null);
  };

  return (
    <Layout eyebrow="Aura Screen" title="Sign in" showTabs={false}>
      <div className={styles.page}>
        <Card className={styles.panel}>
          <div className={styles.heading}>
            <IconBadge tone="rose">
              <KeyRound size={18} strokeWidth={1.6} />
            </IconBadge>
            <div>
              <p className="label tight">Step 1 of 3</p>
              <h2 className={styles.title}>{MODES[mode].title}</h2>
            </div>
          </div>

          <div className={styles.tabs} role="tablist" aria-label="Account">
            {Object.entries(MODES).map(([key, entry]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={mode === key}
                className={`${styles.tab} ${mode === key ? styles.tabActive : ''}`.trim()}
                onClick={() => switchTo(key)}
              >
                {entry.tab}
              </button>
            ))}
          </div>

          {providers?.google && (
            <>
              <GoogleButton
                clientId={providers.googleClientId}
                text={mode === 'register' ? 'signup_with' : 'continue_with'}
                onCredential={withGoogle}
              />
              <p className={styles.divider}>
                <span>or use an email address</span>
              </p>
            </>
          )}

          <CredentialsForm mode={mode} busy={busy} error={error} onSubmit={submit} />

          <Button variant="link" onClick={() => navigate('/welcome')}>
            <ArrowLeft size={15} aria-hidden="true" /> Back to the introduction
          </Button>
        </Card>

        <Card className={styles.aside} accent="sage">
          <div className={styles.heading}>
            <IconBadge>
              <Lock size={17} strokeWidth={1.6} />
            </IconBadge>
            <p className="label tight">How your account is kept</p>
          </div>
          <ul className={styles.notes}>
            <li>Sign in with Google and we receive your name, email and picture — nothing else from your account.</li>
            <li>Choose an email and password instead and the password is hashed with bcrypt, never stored in plain text.</li>
            <li>The session is a signed token in this browser, and only your own record can be read with it.</li>
            <li>Health details and past reports stay against your record until you delete them.</li>
          </ul>
          <p className="muted small">
            Google is only ever asked who you are — Aura Screen requests no access to your mail, files or calendar.
          </p>
        </Card>
      </div>
    </Layout>
  );
}
