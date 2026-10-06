import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LogIn, ShieldCheck } from 'lucide-react';
import { doctorGoogleLogin, doctorLogin, getDoctorToken, getProviders } from '../../api';
import useResource from '../../hooks/useResource';
import GoogleButton from '../../components/GoogleButton';
import Layout from '../../components/Layout';
import { Card, Button, Field } from '../../components/ui';
import styles from './Doctor.module.css';

/**
 * Doctors sign in with Google; the account must already be registered by their clinic,
 * so signing in never creates a doctor. The clinic password stays as a fallback.
 */
export default function DoctorLogin() {
  const navigate = useNavigate();
  const from = useLocation().state?.from;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { data: providers } = useResource(getProviders, []);

  if (getDoctorToken()) return <Navigate to="/doctor" replace />;

  async function signIn(attempt) {
    setBusy(true);
    setError(null);
    try {
      await attempt();
      navigate(from && from.startsWith('/doctor') ? from : '/doctor', { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const submit = (e) => {
    e.preventDefault();
    signIn(() => doctorLogin(email, password));
  };
  const withGoogle = (credential) => signIn(() => doctorGoogleLogin(credential));

  return (
    <Layout eyebrow="Aura Screen · clinician" title="Doctor sign-in" showTabs={false}>
      <Card className={styles.loginCard}>
        <h3>Sign in to see your patients</h3>
        <p className="muted small">Use the Google account your clinic registered for you.</p>

        {providers?.google && (
          <>
            <div className={styles.google}>
              <GoogleButton clientId={providers.googleClientId} text="signin_with" onCredential={withGoogle} />
            </div>
            <p className={styles.divider}>
              <span>or use your clinic password</span>
            </p>
          </>
        )}

        <form className={styles.loginForm} onSubmit={submit}>
          <Field
            label="Work email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Field
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button type="submit" disabled={busy}>
            <LogIn size={15} aria-hidden="true" /> {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
        {error && (
          <p className={styles.formError} role="alert">
            {error}
          </p>
        )}
        <p className="muted small icon-line">
          <ShieldCheck size={13} aria-hidden="true" /> You only see reports that patients have shared with you.
        </p>
      </Card>
    </Layout>
  );
}
