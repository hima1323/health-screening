import { useCallback, useEffect, useMemo, useState } from 'react';
import { PrimaryContext } from './PrimaryContext';
import { getPrimary } from '../api';
import Spinner from '../components/ui/Spinner';
import ErrorState from '../components/ui/ErrorState';

/**
 * Resolves the patient/session ids once, so no screen has to hardcode them. `reload` re-reads them after a
 * scan, so the Report tab opens the newest result.
 */
export function PrimaryProvider({ children }) {
  const [ids, setIds] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(() => getPrimary().then(setIds), []);
  useEffect(() => {
    reload().catch((err) => setError(err.message));
  }, [reload]);
  const value = useMemo(() => ids && { ...ids, reload }, [ids, reload]);

  if (error) {
    return (
      <ErrorState
        message={`Could not reach the API: ${error}`}
        hint="Make sure the server is running and the database has been seeded."
      />
    );
  }

  if (!ids) return <Spinner />;

  return <PrimaryContext.Provider value={value}>{children}</PrimaryContext.Provider>;
}
