/** A reading against a range like "60–100 bpm" (the client's utils/range.js reads ranges the same way). */
function rangeStatus(value, normalRange) {
  const match = normalRange.match(/([\d.]+)\s*[–-]\s*([\d.]+)/);
  if (value > Number(match[2])) return 'Above range';
  if (value < Number(match[1])) return 'Below range';
  return 'Normal';
}

module.exports = { rangeStatus };
