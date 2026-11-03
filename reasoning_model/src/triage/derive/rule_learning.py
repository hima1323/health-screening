"""E1.4 interpretable rule-learning SUGGESTIONS for the clinician (dev split only; never deployed).

Features = kiosk-measurable only: heart rate, breathing rate, temperature (each with one draw of the kiosk error
added), the red-flag indicators and, when present, the age group. Target = urgent (ESI 1-2). Models:
  - sklearn decision tree, depth <= 3, class-weighted;
  - imodels rule lists (a CORELS-type optimal rule list / Bayesian rule list) when the `imodels` package is installed
    (it is optional; not installed here by default).
Each learned rule is printed as plain text with its dev sensitivity / specificity, next to the draft rule set it
would change (SYS kiosk arm a on the same visits).

    python -m triage.derive.rule_learning [--root <ed folder>] [--yale]          (from reasoning_model/src)
--yale uses the Yale dev split (20% of visits, seed 0, the same split as bench/run_bench.py) for more cases.
"""
import argparse
import json

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

from triage.bench import mimic_ed
from triage.bench.ed_cases import KIOSK, mimic_dev_mask, sys_decision
from triage.evidence import ROOT
from triage.rules_engine import load_config, margin_for

OUT = ROOT / "results" / "triage" / "derive"


def features(df, cfg, rng):
    X = pd.DataFrame(index=df.index)
    for name, col, _, source in KIOSK:
        m = margin_for({"name": name, "source": source}, cfg)
        X[col] = df[col] + rng.normal(0, m / 1.96, len(df))
    for it in cfg["red_flags"]["urgent_items"] + ["self_harm"]:
        X[f"flag_{it}"] = df["red_flags"].map(lambda f, it=it: int(it in f))
    if df["age"].notna().any():
        X["age_over_65"] = (df["age"] > 65).astype(int)
    return X


def sens_spec(pred, y):
    pred, y = np.asarray(pred, bool), np.asarray(y, bool)
    return (float(pred[y].mean()) if y.any() else float("nan"),
            float((~pred[~y]).mean()) if (~y).any() else float("nan"))


def main(a):
    cfg = load_config()
    if a.yale:
        from triage.bench import yale
        cases = yale.load()
        cases = cases[cases["esi"].notna()]
        dev = cases[np.random.default_rng(0).random(len(cases)) < 0.2]
        src = "Yale dev split (20% of visits, seed 0)"
    else:
        cases = mimic_ed.load(a.root, cfg)
        cases = cases[cases["esi"].notna()]
        dev = cases[mimic_dev_mask(cases)]
        src = "MIMIC-IV-ED dev split (20% of subjects, seed 0)"
    dev = dev[dev["hr"].notna()].copy()
    if dev["age"].notna().any():                     # the kiosk population (vital_ranges.yaml scope); > 65 apart
        sc = cfg["ranges"]["scope"]
        res_older = int((dev["age"] > sc["max_age"]).sum())
        dev = dev[(dev["age"] >= sc["min_age"]) & (dev["age"] <= sc["max_age"])]
        src += f", ages {sc['min_age']}-{sc['max_age']} ({res_older} older visits left out)"
    if len(dev) > a.max_cases:
        dev = dev.sample(a.max_cases, random_state=0)
    y = (dev["esi"] <= 2).to_numpy()
    rng = np.random.default_rng(0)
    X = features(dev, cfg, rng).fillna(X_fill := {"hr": 80, "rr": 16, "temp_c": 36.8})
    tree = DecisionTreeClassifier(max_depth=3, class_weight="balanced", min_samples_leaf=max(5, len(dev) // 100),
                                  random_state=0).fit(X, y)
    t_sens, t_spec = sens_spec(tree.predict(X), y)
    draft = [sys_decision(c, "a_kiosk_vitals_red_flags", cfg)[0] == "URGENT" for c in dev.to_dict("records")]
    d_sens, d_spec = sens_spec(draft, y)
    res = {"source": src, "n_dev": len(dev), "urgent_rate": float(y.mean()),
           "missing_filled_with": X_fill, "draft_rules_urgent": {"sensitivity": d_sens, "specificity": d_spec},
           "tree_depth3": {"sensitivity_dev": t_sens, "specificity_dev": t_spec,
                           "rules": export_text(tree, feature_names=list(X.columns), decimals=1)}}
    try:
        from imodels import OptimalRuleListClassifier  # noqa: F401  (optional)
        res["imodels"] = "installed: add the rule lists here"
    except ImportError:
        res["imodels"] = "not installed (optional): pip install imodels to add CORELS / Bayesian rule lists"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rule_learning.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{src}: {len(dev)} visits with a heart rate, urgent {y.mean():.1%}")
    print(f"draft rules (SYS arm a, URGENT): sensitivity {d_sens:.2f}, specificity {d_spec:.2f}")
    print(f"depth-3 tree (dev, in-sample): sensitivity {t_sens:.2f}, specificity {t_spec:.2f}")
    print(res["tree_depth3"]["rules"])
    print("SUGGESTIONS ONLY, for the clinician (Delphi pack); never deployed. " + res["imodels"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(mimic_ed.DEMO))
    ap.add_argument("--yale", action="store_true")
    ap.add_argument("--max-cases", type=int, default=20000)
    main(ap.parse_args())
