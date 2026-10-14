import { useContext } from 'react';
import { PrefsContext } from '../context/PrefsContext';

/** Language and colour-blind mode, plus `t(english)` → the text in the chosen language. */
export default function usePrefs() {
  return useContext(PrefsContext);
}
