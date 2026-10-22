import { createContext } from 'react';

/** The patient's display preferences — language and colour-blind mode; the provider lives in PrefsProvider.jsx. */
export const PrefsContext = createContext({ lang: 'en', vision: 'normal', colourBlind: false, t: (s) => s });
