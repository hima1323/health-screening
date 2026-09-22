import { useCallback, useEffect, useMemo, useState } from 'react';
import { AuthContext } from './AuthContext';
import { getCurrentUser, login, register, signInWithGoogle, signOut as clearToken } from '../api';
import { getToken } from '../api/client';
import Spinner from '../components/ui/Spinner';

/**
 * Holds the signed-in patient for the whole app.
 *
 * While a remembered token is being checked the app shows a spinner; afterwards
 * `user` is either the signed-in patient or null.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [restoring, setRestoring] = useState(Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;

    getCurrentUser()
      .then((restored) => {
        if (!cancelled) setUser(restored);
      })
      .catch(() => {
        clearToken(); // the token no longer resolves — start over at the welcome screen
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (credentials) => {
    const signedIn = await login(credentials);
    setUser(signedIn);
    return signedIn;
  }, []);

  const createAccount = useCallback(async (credentials) => {
    const created = await register(credentials);
    setUser(created);
    return created;
  }, []);

  const signInWithGoogleCredential = useCallback(async (credential) => {
    const signedIn = await signInWithGoogle(credential);
    setUser(signedIn);
    return signedIn;
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, signIn, createAccount, signInWithGoogleCredential, signOut, applyUser: setUser }),
    [user, signIn, createAccount, signInWithGoogleCredential, signOut]
  );

  if (restoring) return <Spinner />;

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
