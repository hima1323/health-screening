import { NavLink } from 'react-router-dom';
import { Leaf } from 'lucide-react';
import StillWaterScene from '../StillWaterScene';
import AccountChip from '../AccountChip';
import styles from './Layout.module.css';

const TABS = [
  { to: '/', label: 'Scan Hub', end: true },
  { to: '/report', label: 'Session Report' },
  { to: '/timeline', label: 'Biometric Timeline' },
];

/**
 * The page shell: backdrop, header, tab strip and main column.
 * The onboarding screens pass `showTabs={false}` — there is nowhere to navigate yet.
 */
export default function Layout({ eyebrow, title, badge, showTabs = true, children }) {
  return (
    <div className={styles.shell}>
      <StillWaterScene />

      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            <Leaf size={19} strokeWidth={1.6} />
          </span>
          <div>
            <p className={styles.eyebrow}>{eyebrow}</p>
            <h1 className={styles.title}>{title}</h1>
          </div>
        </div>
        <div className={styles.headerEnd}>
          {badge}
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
              className={({ isActive }) => `${styles.tab} ${isActive ? styles.tabActive : ''}`.trim()}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}

      <main className={styles.main}>{children}</main>
    </div>
  );
}
