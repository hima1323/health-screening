import styles from './PhaseTable.module.css';

const show = (v, digits) => (v === null || v === undefined ? '—' : Number(v).toFixed(digits));

/**
 * Every metric, phase by phase, with the change from first to last.
 * The change is tinted by whether it moved the healthy way for that metric.
 */
export default function PhaseTable({ metricDefs, metrics }) {
  const phases = metrics.map((m) => m.phase);
  const first = metrics[0]?.values ?? {};
  const last = metrics[metrics.length - 1]?.values ?? {};
  const showDelta = metrics.length > 1;

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {phases.map((p) => (
              <th scope="col" key={p}>{p}</th>
            ))}
            {showDelta && <th scope="col">Change</th>}
          </tr>
        </thead>
        <tbody>
          {metricDefs.map((def) => {
            const a = first[def.key];
            const b = last[def.key];
            const delta = a !== null && a !== undefined && b !== null && b !== undefined ? b - a : null;
            // only metrics with a healthy direction get tinted, and no change is never a regression
            const better = delta && def.lowerIsBetter ? delta < 0 : null;
            return (
              <tr key={def.key}>
                <th scope="row">
                  {def.label}
                  {def.unit && <span className={styles.unit}> {def.unit}</span>}
                </th>
                {metrics.map((m) => (
                  <td key={m.phase}>{show(m.values[def.key], def.digits)}</td>
                ))}
                {showDelta && (
                  <td className={better === true ? styles.good : better === false ? styles.bad : styles.delta}>
                    {delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(def.digits)}`}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
