import { HI, HI_PATTERNS } from './hi';

// in development, every string without a translation is collected here so gaps can be found and filled
const missing = import.meta.env.DEV ? new Set() : null;
if (missing && typeof window !== 'undefined') window.__i18nMissing = missing;

/**
 * English text → the chosen language. The English string is the key, so text that comes from the server
 * (statuses, notes, summaries) translates the same way as the app's own labels; strings with numbers in them go
 * through patterns. Anything unknown is shown in English rather than not at all.
 */
export function translate(text, lang) {
  if (lang !== 'hi' || typeof text !== 'string' || !text.trim()) return text;
  const key = text.trim();
  if (!/[A-Za-z]{2,}/.test(key)) return text;
  if (HI[key]) return HI[key];
  for (const [pattern, render] of HI_PATTERNS) {
    const match = key.match(pattern);
    if (match) return render(match, (part) => translate(part, lang));
  }
  missing?.add(key);
  return text;
}
