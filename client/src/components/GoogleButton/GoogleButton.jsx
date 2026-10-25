import { useEffect, useRef, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { SocialLogin } from '@capgo/capacitor-social-login';
import Button from '../ui/Button';
import styles from './GoogleButton.module.css';

const LABELS = {
  continue_with: 'Continue with Google',
  signup_with: 'Sign up with Google',
  signin_with: 'Sign in with Google',
};

/**
 * Google's own rendered sign-in button (Google Identity Services).
 *
 * It hands back a signed ID token, which `onCredential` sends to the API for
 * verification. Google requires its own button markup, so this mounts theirs.
 * Google refuses GIS inside the Android app's web view, so there it signs in
 * natively instead — the ID token is for the same web client ID either way.
 */
export default function GoogleButton(props) {
  return Capacitor.isNativePlatform() ? <NativeGoogleButton {...props} /> : <WebGoogleButton {...props} />;
}

function NativeGoogleButton({ clientId, text = 'continue_with', onCredential }) {
  const [error, setError] = useState(null);

  const signIn = async () => {
    setError(null);
    try {
      await SocialLogin.initialize({ google: { webClientId: clientId } });
      const { result } = await SocialLogin.login({ provider: 'google', options: { scopes: ['email', 'profile'] } });
      onCredential(result.idToken);
    } catch (err) {
      // closing Google's account sheet is not an error worth showing
      if (!/cancel/i.test(err.message)) setError(err.message);
    }
  };

  return (
    <div className={styles.slot}>
      <Button onClick={signIn}>{LABELS[text] || LABELS.continue_with}</Button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

function WebGoogleButton({ clientId, text = 'continue_with', onCredential }) {
  const slot = useRef(null);
  const callback = useRef(onCredential);

  // kept in a ref so a new handler identity never re-renders Google's button
  useEffect(() => {
    callback.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!clientId) return;

    // the GIS script is loaded async in index.html, so it may not be here yet
    const mount = () => {
      const gis = window.google?.accounts?.id;
      if (!gis || !slot.current) return false;

      gis.initialize({ client_id: clientId, callback: (res) => callback.current(res.credential) });
      gis.renderButton(slot.current, { theme: 'outline', size: 'large', width: 320, text, shape: 'pill' });
      return true;
    };

    if (mount()) return;
    const timer = setInterval(() => mount() && clearInterval(timer), 100);
    return () => clearInterval(timer);
  }, [clientId, text]);

  return <div className={styles.slot} ref={slot} />;
}
