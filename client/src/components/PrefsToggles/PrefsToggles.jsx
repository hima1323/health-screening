import { Eye } from 'lucide-react';
import usePrefs from '../../hooks/usePrefs';
import styles from './PrefsToggles.module.css';

const VISIONS = [
  ['normal', 'Normal colours'],
  ['safe', 'Colour-blind safe colours'],
  ['protanopia', 'Preview: protanopia (red-blind)'],
  ['deuteranopia', 'Preview: deuteranopia (green-blind)'],
];

/**
 * Header controls: English / हिंदी, and colours — normal, a colour-blind-safe palette, or a preview of how the page
 * looks with protanopia or deuteranopia.
 */
export default function PrefsToggles() {
  const { lang, setLang, vision, setVision, t } = usePrefs();

  return (
    <div className={styles.toggles}>
      <div className={styles.segment} role="group" aria-label="Language / भाषा">
        <button type="button" lang="en" aria-pressed={lang === 'en'} onClick={() => setLang('en')}>
          EN
        </button>
        <button type="button" lang="hi" aria-pressed={lang === 'hi'} onClick={() => setLang('hi')}>
          हिं
        </button>
      </div>

      {/* a native select: keyboard, screen readers and the phone's own picker all work without extra code */}
      <label className={`${styles.vision} ${vision !== 'normal' ? styles.on : ''}`.trim()} title={t('Colours')}>
        <Eye size={17} strokeWidth={1.8} aria-hidden="true" />
        <select value={vision} onChange={(e) => setVision(e.target.value)} aria-label={t('Colours')}>
          {VISIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {t(label)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
