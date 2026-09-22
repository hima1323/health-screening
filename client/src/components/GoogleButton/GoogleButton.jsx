import { useEffect, useRef } from 'react';
import styles from './GoogleButton.module.css';

/**
 * Google's own rendered sign-in button (Google Identity Services).
 *
 * It hands back a signed ID token, which `onCredential` sends to the API for
 * verification. Google requires its own button markup, so this mounts theirs.
 */
export default function GoogleButton({ clientId, text = 'continue_with', onCredential }) {
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
