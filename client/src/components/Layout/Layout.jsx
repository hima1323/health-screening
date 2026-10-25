import { useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, ClipboardList, Leaf, ScanFace } from 'lucide-react';
import StillWaterScene from '../StillWaterScene';
import AccountChip from '../AccountChip';
import usePageTitle from '../../hooks/usePageTitle';
import usePrefs from '../../hooks/usePrefs';
import PrefsToggles from '../PrefsToggles';
import styles from './Layout.module.css';

const TABS = [
  { to: '/', label: 'Scan Hub', short: 'Scan', icon: ScanFace, end: true },
  { to: '/report', label: 'Session Report', short: 'Report', icon: ClipboardList },
  { to: '/timeline', label: 'Biometric Timeline', short: 'Timeline', icon: Activity },
];

/**
 * The page shell: backdrop, header, tab strip and main column.
 * The onboarding screens pass `showTabs={false}` — there is nowhere to navigate yet;
 * the welcome screen also drops the language / colour toggles (`showPrefs={false}`).
 * On a phone-sized screen the tab strip becomes a bottom tab bar.
 */
export default function Layout({ eyebrow, title, pageTitle, badge, showTabs = true, showPrefs = true, children }) {
  // the tab title: `pageTitle` when the heading alone isn't unique
  const { lang, t } = usePrefs();
  usePageTitle(t(pageTitle ?? (typeof title === 'string' ? title : undefined)), t('Aura Screen'));
  // screen readers pick their voice from the page language
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return (
    <div className={`${styles.shell} ${showTabs ? styles.withTabs : ''}`.trim()}>
      <StillWaterScene />

      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            <Leaf size={19} strokeWidth={1.6} />
          </span>
          <div>
            <p className={styles.eyebrow}>{t(eyebrow)}</p>
            <h1 className={styles.title}>{t(title)}</h1>
          </div>
        </div>
        <div className={styles.headerEnd}>
          {badge}
          {showPrefs && (
            <div className={styles.prefs}>
              <PrefsToggles />
            </div>
          )}
          <AccountChip />
        </div>
      </header>

      {showTabs && (
        <nav className={styles.tabs}>
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              aria-label={t(tab.label)}
              className={({ isActive }) => `${styles.tab} ${isActive ? styles.tabActive : ''}`.trim()}
            >
              <tab.icon className={styles.tabIcon} size={16} strokeWidth={1.7} aria-hidden="true" />
              <span className={styles.tabLabel}>{t(tab.label)}</span>
              <span className={styles.tabShort}>{t(tab.short)}</span>
            </NavLink>
          ))}
        </nav>
      )}

      <main className={styles.main}>{children}</main>
    </div>
  );
}
