import styles from './HeroBanner.module.css';
import usePrefs from '../../hooks/usePrefs';

/** The session page's opening banner: how many readings are fine, at a glance. */
export default function HeroBanner({ readings, minutes, sensors }) {
  const { lang, t } = usePrefs();
  const fine = readings.filter((r) => r.ok).length;

  return (
    <section className={styles.hero} aria-label={t('Your session in one look')}>
      <div className={styles.text}>
        <p className={styles.kicker}>{t('Your session in one look')}</p>
        {/* "2 of 4" in English, "4 में से 2" in Hindi */}
        <p className={styles.big}>
          {lang === 'hi' ? (
            <>
              <span>{t(`of ${readings.length}`)} </span>
              {fine}
            </>
          ) : (
            <>
              {fine}
              <span> {t(`of ${readings.length}`)}</span>
            </>
          )}
        </p>
        <p className={styles.sub}>{t('readings are fine')}</p>
        <p className={styles.meta}>
          {t(`${minutes} min recorded · ${sensors} sensors`)}
        </p>
      </div>
    </section>
  );
}
