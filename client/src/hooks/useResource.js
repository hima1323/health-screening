import { useEffect, useState } from 'react';

/**
 * Loads one API resource and tracks its error state.
 * `deps` behaves like a useEffect dependency list — the resource reloads when it changes.
 */
export default function useResource(loader, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    loader()
      .then((result) => active && setData(result))
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error };
}
