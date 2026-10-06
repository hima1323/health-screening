/**
 * Where a reading sits against a range like "72–96 bpm".
 * Returns { low, high, position: 'below' | 'within' | 'above' }, or null if the range can't be read.
 */
export function rangePosition(value, normalRange) {
  const match = normalRange?.match(/([\d.]+)\s*[–-]\s*([\d.]+)/);
  if (!match || value == null) return null;
  const low = Number(match[1]);
  const high = Number(match[2]);
  const position = value > high ? 'above' : value < low ? 'below' : 'within';
  return { low, high, position };
}
