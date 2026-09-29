/*
 * Colour maps for thermograms, after Hans's thermal explorer. Inferno is
 * perceptually uniform with monotonic lightness and reads correctly for
 * colour-blind viewers; grayscale is the plain alternative. No rainbow maps —
 * they invent edges in smooth temperature fields.
 */
const INFERNO = ['#000004', '#1b0c41', '#4a0c6b', '#781c6d', '#a52c60', '#cf4446', '#ed6925', '#fb9b06', '#f7d13d', '#fcffa4'];
const GRAY = ['#000000', '#ffffff'];

function buildLut(stops) {
  const rgb = stops.map((hex) => {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  });
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const p = (i / 255) * (rgb.length - 1);
    const k = Math.min(rgb.length - 2, Math.floor(p));
    const f = p - k;
    for (let c = 0; c < 3; c += 1) lut[i * 3 + c] = rgb[k][c] + (rgb[k + 1][c] - rgb[k][c]) * f;
  }
  return lut;
}

export const COLORMAPS = {
  inferno: { label: 'Inferno', lut: buildLut(INFERNO), css: INFERNO },
  gray: { label: 'Grayscale', lut: buildLut(GRAY), css: GRAY },
};

export const gradientCss = (key) => `linear-gradient(to right, ${COLORMAPS[key].css.join(', ')})`;
