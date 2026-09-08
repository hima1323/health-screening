import { useEffect, useState } from 'react';

/**
 * Counts a live capture down to zero, one second at a time.
 * Returns `null` until `from` is known, so callers can tell "not started" from "finished".
 */
export default function useCountdown(from) {
  const [remaining, setRemaining] = useState(null);

  useEffect(() => {
    if (from === undefined || from === null) return;
    setRemaining(from);
  }, [from]);

  useEffect(() => {
    if (remaining === null || remaining <= 0) return;
    const timer = setTimeout(() => setRemaining((s) => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(timer);
  }, [remaining]);

  return remaining;
}
