import { useCallback, useEffect, useMemo, useState } from 'react';
import { PrefsContext } from './PrefsContext';
import { translate } from '../i18n';

const KEY = 'aura-screen.prefs';

// a per-browser convenience: private browsing or blocked storage just falls back to the defaults
function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY)) || {};
    // earlier versions stored a plain on/off
    if (saved.vision === undefined && saved.colourBlind) saved.vision = 'safe';
    return saved;
  } catch {
    return {};
  }
}

/**
 * How colours are shown, Machado et al. (2009) full-severity matrices — the same simulation Chrome DevTools uses for
 * "Emulate vision deficiencies". 'safe' instead swaps the palette for a colour-blind-safe one (index.css).
 */
const SIMULATIONS = {
  protanopia: '0.152 1.053 -0.205 0 0  0.115 0.786 0.099 0 0  -0.004 -0.048 1.052 0 0  0 0 0 1 0',
  deuteranopia: '0.367 0.861 -0.228 0 0  0.280 0.673 0.047 0 0  -0.012 0.043 0.969 0 0  0 0 0 1 0',
};

/** Language (English / Hindi) and colour vision ('normal' | 'safe' | 'protanopia' | 'deuteranopia'), remembered here. */
export function PrefsProvider({ children }) {
  const [prefs, setPrefs] = useState(() => ({ lang: 'en', vision: 'normal', ...load() }));

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      /* not saved — still applies until reload */
    }
    // 'safe' swaps the palette tokens; the previews filter the whole page through a simulation (index.css)
    document.documentElement.dataset.vision = prefs.vision === 'safe' ? 'cb' : '';
    document.documentElement.dataset.simulate = SIMULATIONS[prefs.vision] ? prefs.vision : '';
  }, [prefs]);

  const setLang = useCallback((lang) => setPrefs((p) => ({ ...p, lang })), []);
  const setVision = useCallback((vision) => setPrefs((p) => ({ ...p, vision })), []);
  const t = useCallback((text) => translate(text, prefs.lang), [prefs.lang]);

  const value = useMemo(
    () => ({ ...prefs, colourBlind: prefs.vision === 'safe', setLang, setVision, t }),
    [prefs, setLang, setVision, t]
  );
  return (
    <PrefsContext.Provider value={value}>
      {children}
      {/* the filters the previews point at */}
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
        {Object.entries(SIMULATIONS).map(([id, matrix]) => (
          <filter key={id} id={`simulate-${id}`} colorInterpolationFilters="linearRGB">
            <feColorMatrix type="matrix" values={matrix} />
          </filter>
        ))}
      </svg>
    </PrefsContext.Provider>
  );
}
