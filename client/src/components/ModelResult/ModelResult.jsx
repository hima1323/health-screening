import { Brain, Send } from 'lucide-react';
import { Card, CardRow, CardHeading, IconBadge, StatusPill } from '../ui';
import styles from './ModelResult.module.css';

const pct = (x) => `${Math.round(x * 100)}%`;
const signed = (x) => (Math.abs(x) < 0.005 ? '0.00' : `${x > 0 ? '+' : '−'}${Math.abs(x).toFixed(2)}`);

/**
 * The full reasoning-model output for a live scan, for the doctor: the call, how sure, which sensor agents
 * pushed it which way (exact log-odds contributions of the fusion model), each 30 s window, the strongest
 * features behind it, and where the data came from.
 */
export default function ModelResult({ model }) {
  const { summary, windows, transfer, trainedOnSubjects } = model;
  const call = summary.abstain ? 'No clear reading' : `${summary.label === 'high' ? 'High' : 'Low'} mental load`;
  const agents = summary.agents.filter((a) => a.windows > 0);
  const off = summary.agents.filter((a) => a.windows === 0);
  const scale = Math.max(...agents.map((a) => Math.abs(a.contribution)), 0.5);

  return (
    <Card className={styles.card}>
      <CardRow>
        <CardHeading>
          <IconBadge tone={summary.label === 'high' && !summary.abstain ? 'amber' : undefined}>
            <Brain size={17} strokeWidth={1.7} />
          </IconBadge>
          <div>
            <h3>Reasoning model</h3>
            <p className="muted small">8 sensor agents (LightGBM) + fusion · trained on {trainedOnSubjects} other people</p>
          </div>
        </CardHeading>
        <StatusPill dot={false}>{call}</StatusPill>
      </CardRow>

      <div className={styles.headline}>
        <div>
          <p className={styles.big}>{pct(summary.confidence)}</p>
          <p className="muted small">confidence</p>
        </div>
        <div>
          <p className={styles.big}>{summary.probability_high.toFixed(2)}</p>
          <p className="muted small">P(high load)</p>
        </div>
        <div>
          <p className={styles.big}>{summary.windows}</p>
          <p className="muted small">windows of 30 s</p>
        </div>
      </div>

      <p className={styles.explanation}>{summary.explanation}</p>

      <section>
        <p className="label">Which sensors decided it · average log-odds push</p>
        <div className={styles.axisLabels} aria-hidden="true">
          <span>← toward low load</span>
          <span>toward high load →</span>
        </div>
        <ul className={styles.bars}>
          {agents.map((a) => {
            const width = (Math.abs(a.contribution) / scale) * 50;
            const high = a.contribution > 0;
            return (
              <li key={a.modality} title={`${a.label}: ${signed(a.contribution)} log-odds toward ${high ? 'high' : 'low'} load`}>
                <span className={styles.barName}>{a.label}</span>
                <span className={styles.track}>
                  <span
                    className={`${styles.bar} ${high ? styles.toHigh : styles.toLow}`}
                    style={high ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
                  />
                </span>
                <span className={styles.barValue}>{signed(a.contribution)}</span>
              </li>
            );
          })}
        </ul>
        {off.length > 0 && (
          <p className="muted small">Not used (missing or below the quality gate): {off.map((a) => a.label).join(', ')}</p>
        )}
      </section>

      <section>
        <p className="label">Each 30 s window · P(high load), line at 0.5</p>
        <div className={styles.windows}>
          {windows.map((w, i) => (
            <div
              key={i}
              className={styles.window}
              title={`Window ${i + 1} (${i * 15}–${i * 15 + 30} s): P(high) ${w.probability_high.toFixed(2)}${w.abstain ? ' · abstains' : ''}`}
            >
              <span className={styles.windowValue}>{w.probability_high.toFixed(2)}</span>
              <span className={styles.windowTrack}>
                <span
                  className={`${styles.windowBar} ${w.probability_high >= 0.5 ? styles.toHigh : styles.toLow}`}
                  style={{ height: `${Math.max(w.probability_high * 100, 2)}%` }}
                />
              </span>
              <span className="muted small">{i * 15} s</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <p className="label">Strongest evidence · mean over the windows</p>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Feature</th>
              <th>Value</th>
              <th>vs rest</th>
              <th>Pushes</th>
            </tr>
          </thead>
          <tbody>
            {evidence(windows).map((f) => (
              <tr key={f.feature}>
                <td>
                  {f.description}
                  <span className="muted small"> · {f.agent}</span>
                </td>
                <td>
                  {f.value == null ? '—' : round(f.value)} <span className="muted small">{f.unit}</span>
                </td>
                <td>{f.z == null ? '—' : `${f.z > 0 ? '+' : ''}${f.z.toFixed(1)} SD`}</td>
                <td>{f.shap > 0 ? 'high' : 'low'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className={styles.provenance}>
        <p className="muted small icon-line">
          <Send size={13} aria-hidden="true" />
          <span>
            {(transfer.bytes / 1024).toFixed(1)} KB sent to the model server · answered in {transfer.modelMs} ms
          </span>
        </p>
      </div>
    </Card>
  );
}

const round = (x) => (Math.abs(x) >= 100 ? x.toFixed(0) : Math.abs(x) >= 1 ? x.toFixed(1) : x.toFixed(3));

/** The features the agents leaned on most, pooled over windows: mean |SHAP| decides the order. */
function evidence(windows, top = 6) {
  const pooled = new Map();
  windows.forEach((w) =>
    w.agents
      .filter((a) => a.available)
      .forEach((a) =>
        a.top_features.forEach((f) => {
          const p = pooled.get(f.feature) ?? { ...f, agent: a.label, n: 0, shap: 0, z: 0, value: 0, abs: 0 };
          p.n += 1;
          p.abs += Math.abs(f.shap ?? 0);
          p.shap += f.shap ?? 0;
          p.z += f.z ?? 0;
          p.value += f.value ?? 0;
          pooled.set(f.feature, p);
        })
      )
  );
  return [...pooled.values()]
    .map((p) => ({ ...p, shap: p.shap / p.n, z: p.z / p.n, value: p.value / p.n, abs: p.abs / windows.length }))
    .sort((a, b) => b.abs - a.abs)
    .slice(0, top);
}
