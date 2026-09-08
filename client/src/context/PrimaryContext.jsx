import { createContext, useEffect, useState } from 'react';
import { getPrimary } from '../api';
import Spinner from '../components/ui/Spinner';
import ErrorState from '../components/ui/ErrorState';

export const PrimaryContext = createContext(null);

/**
 * Resolves the demo patient/session ids once, so no screen has to hardcode them.
 */
export function PrimaryProvider({ children }) {
  const [ids, setIds] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getPrimary().then(setIds).catch((err) => setError(err.message));
  }, []);

  if (error) {
    return (
      <ErrorState
        message={`Could not reach the API: ${error}`}
        hint="Make sure the server is running and the database has been seeded."
      />
    );
  }

  if (!ids) return <Spinner />;

  return <PrimaryContext.Provider value={ids}>{children}</PrimaryContext.Provider>;
}
