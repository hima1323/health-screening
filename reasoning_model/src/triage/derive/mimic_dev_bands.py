"""E1.2 MIMIC-IV-ED dev analysis: how urgent-visit rates change across vital-sign bands, how well each draft cut-off
separates urgent visits (with and without the kiosk's measurement error), and how the red flags cover the chief
complaints. Dev split only (ed_cases.mimic_dev_mask: a fixed random 20% of subjects); the benchmark never tests on
those subjects. Runs on the open Demo now; on the full release (data use agreement; data/restricted/, never sent to
any external service) with --root. Outputs are aggregates only, in results/triage/derive/.

Outcome "urgent" = ESI 1-2. Also reported: admitted. ICU / death within 48 h needs the hosp/icu modules (not in the
ED Demo): reported as not available. Age is not in the ED module either (the full release links patients.anchor_age):
by-age tables appear when an `age` column is present.

    python -m triage.derive.mimic_dev_bands [--root <ed folder>] [--draws 10]          (from reasoning_model/src)
"""
import argparse
import json
from collections import Counter

import numpy as np
import pandas as pd

from triage.bench import mimic_ed
from triage.bench.ed_cases import KIOSK, all_kiosk_vitals_normal, mimic_dev_mask
from triage.evidence import ROOT
from triage.rules_engine import load_config, margin_for

OUT = ROOT / "results" / "triage" / "derive"
BANDS = {"hr": 5, "rr": 2, "temp_c": 0.2, "spo2": 1, "sbp": 10}
NAMES = {"hr": "heart_rate", "rr": "resp_rate", "temp_c": "temperature", "spo2": "spo2", "sbp": "sbp"}
SOURCES = {"heart_rate": "rppg", "resp_rate": "thermal_nostril", "temperature": "thermal_canthus",
           "spo2": "device", "sbp": "device"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def band_table(df, col, width, outcome="urgent"):
    x = df[[col, outcome]].dropna()
    lo = np.floor(x[col] / width) * width
    rows = []
    for b, g in x.groupby(lo):
        p, l, h = wilson(int(g[outcome].sum()), len(g))
        rows.append({"band_from": round(float(b), 2), "band_to": round(float(b + width), 2), "n": len(g),
                     "urgent_rate": p, "ci_low": l, "ci_high": h})
    return pd.DataFrame(rows)


def cutoffs(cfg, col):
    spec = cfg["ranges"]["measures"][NAMES[col]]
    out = []
    for kind in ("normal", "urgent"):
        lo, hi = spec[kind]
        if lo is not None:
            out.append((f"{kind} low (< {lo})", lambda v, lo=lo: v < lo))
        if hi is not None:
            out.append((f"{kind} high (> {hi})", lambda v, hi=hi: v > hi))
    return out


def cutoff_performance(df, cfg, col, draws, rng):
    """Sensitivity (urgent visits flagged) and false-positive rate (non-urgent flagged) of each draft cut-off, on the
    recorded value and averaged over `draws` kiosk-error draws (value + N(0, (margin / 1.96)^2))."""
    x = df[[col, "urgent"]].dropna()
    v, y = x[col].to_numpy(float), x["urgent"].to_numpy(bool)
    m = margin_for({"name": NAMES[col], "source": SOURCES[NAMES[col]]}, cfg)
    rows = []
    for label, flag in cutoffs(cfg, col):
        f = flag(v)
        noisy = [flag(v + rng.normal(0, m / 1.96, len(v))) for _ in range(draws)]
        rows.append({"cutoff": label, "n": len(v), "n_urgent": int(y.sum()),
                     "sensitivity": float(f[y].mean()) if y.any() else float("nan"),
                     "false_positive_rate": float(f[~y].mean()) if (~y).any() else float("nan"),
                     "sensitivity_with_kiosk_error": float(np.mean([n[y].mean() for n in noisy])) if y.any() else
                     float("nan"),
                     "fpr_with_kiosk_error": float(np.mean([n[~y].mean() for n in noisy])) if (~y).any() else
                     float("nan"), "kiosk_margin": m})
    return pd.DataFrame(rows)


def red_flag_tables(df, cfg):
    items = cfg["red_flags"]["urgent_items"] + ["self_harm"]
    per = []
    for it in items:
        has = df["red_flags"].map(lambda f, it=it: it in f)
        p, l, h = wilson(int(df.loc[has, "urgent"].sum()), int(has.sum()))
        per.append({"red_flag": it, "n_visits": int(has.sum()), "urgent_rate": p, "ci_low": l, "ci_high": h})
    urgent = df[df["urgent"]]
    missed = urgent[(urgent["red_flags"].map(len) == 0) & urgent.apply(lambda r: all_kiosk_vitals_normal(r, cfg),
                                                                        axis=1)]
    unmapped = df[df["red_flags"].map(len) == 0]
    top = Counter(unmapped["complaint"].str.lower().str.strip()).most_common(50)
    return pd.DataFrame(per), {
        "n_urgent": len(urgent),
        "urgent_no_red_flag_and_normal_kiosk_vitals": len(missed) / len(urgent) if len(urgent) else float("nan"),
        "unmapped_complaint_share": len(unmapped) / len(df) if len(df) else float("nan")}, top


def plot(df, cfg, col, width, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = band_table(df, col, width)
    if t.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 3.6))
    mid = (t["band_from"] + t["band_to"]) / 2
    ax.errorbar(mid, t["urgent_rate"], yerr=[t["urgent_rate"] - t["ci_low"], t["ci_high"] - t["urgent_rate"]],
                fmt="o", color="#2c3e50", ms=4, capsize=2, label="urgent rate (ESI 1-2), Wilson 95% CI")
    spec = cfg["ranges"]["measures"][NAMES[col]]
    for kind, style in (("normal", "--"), ("urgent", ":")):
        for v in spec[kind]:
            if v is not None:
                ax.axvline(v, ls=style, color="#c0392b" if kind == "urgent" else "#e67e22", lw=1)
    ax.set(xlabel=f"{NAMES[col]} (dashed: draft normal range, dotted: draft urgent range)", ylabel="share urgent",
           ylim=(0, 1), title=f"MIMIC-IV-ED dev split: urgent rate by {NAMES[col]} band (n={int(t['n'].sum())})")
    ax.legend(loc="upper center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(a):
    cfg = load_config()
    cases = mimic_ed.load(a.root, cfg)
    cases = cases[cases["esi"].notna()].copy()
    dev = cases[mimic_dev_mask(cases)].copy()
    dev["urgent"] = dev["esi"] <= 2
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    res = {"split": "dev = 20% of subjects (seed 0); the benchmark tests on the other 80%",
           "n_visits_dev": len(dev), "n_subjects_dev": int(dev["patient_id"].nunique()),
           "urgent_rate": float(dev["urgent"].mean()), "admitted_rate": float(dev["admitted"].mean()),
           "icu_or_death_48h": "not available in the ED module (needs hosp / icu)",
           "margins_status": cfg["ranges"]["error_margins"]["status"], "cutoffs": {}, "by_age": "no age column"}
    for col, width in BANDS.items():
        band_table(dev, col, width).to_csv(OUT / f"mimic_dev_bands_{NAMES[col]}.csv", index=False)
        perf = cutoff_performance(dev, cfg, col, a.draws, rng)
        res["cutoffs"][NAMES[col]] = perf.to_dict("records")
        plot(dev, cfg, col, width, OUT / f"mimic_dev_bands_{NAMES[col]}.png")
    if dev["age"].notna().any():
        dev["age_group"] = pd.cut(dev["age"], [17, 40, 65, 200], labels=["18-40", "41-65", ">65"])
        res["by_age"] = {str(g): {"n": len(x), "urgent_rate": float(x["urgent"].mean())}
                         for g, x in dev.groupby("age_group", observed=True)}
    per, cover, top = red_flag_tables(dev, cfg)
    per.to_csv(OUT / "mimic_dev_red_flags.csv", index=False)
    res["red_flags"] = cover
    pd.DataFrame(top, columns=["complaint", "n"]).to_csv(OUT / "mimic_dev_unmapped_complaints_top50.csv", index=False)
    (OUT / "mimic_dev_summary.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"dev: {res['n_visits_dev']} visits, {res['n_subjects_dev']} subjects; urgent (ESI 1-2) "
          f"{res['urgent_rate']:.1%}, admitted {res['admitted_rate']:.1%}")
    print(f"{'cut-off':<34} {'n':>5} {'sens':>6} {'FPR':>6} {'sens+err':>9} {'FPR+err':>8}")
    for name, rows in res["cutoffs"].items():
        for r in rows:
            print(f"{name + ' ' + r['cutoff']:<34} {r['n']:5d} {r['sensitivity']:6.2f} {r['false_positive_rate']:6.2f} "
                  f"{r['sensitivity_with_kiosk_error']:9.2f} {r['fpr_with_kiosk_error']:8.2f}")
    print(f"red flags: urgent visits with no red flag AND normal kiosk vitals (the kiosk would miss): "
          f"{cover['urgent_no_red_flag_and_normal_kiosk_vitals']:.1%} of {cover['n_urgent']}; complaints mapping to "
          f"no red flag: {cover['unmapped_complaint_share']:.1%}")
    print(per.to_string(index=False))
    print(f"-> {OUT.relative_to(ROOT)} (aggregates only; the dev numbers on the Demo are small and only test the code)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(mimic_ed.DEMO))
    ap.add_argument("--draws", type=int, default=10)
    main(ap.parse_args())
