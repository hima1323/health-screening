"""Vignette benchmark (starter kit phase E6, the core decision test).

Vignettes: YAML lists in vignettes/*.yaml in the format of templates/vignette_template.yaml. Reference labels come
from 2-3 clinicians, blind to the rules (clinician_labels: rater1..3 + consensus); vignettes without a consensus are
run but left out of the metrics. Format notes (load_vignettes normalises them):
  - bare yes/no in YAML are booleans: they are turned back into "yes"/"no";
  - a measurement given as one number = two equal readings (the repeat agrees); a list = the readings; null = not
    measured; systolic_bp / diastolic_bp = sbp / dbp;
  - optional measurements_after_rest: the readings used if SYS asks for a REMEASURE (default: the same readings);
  - age is stored as an answer (scope rule R00), scores as given, flags (e.g. face_not_found) as given.

Arms (all on the same vignettes): SYS (locked rule engine with one REMEASURE round), D0 always refer, D1 vitals only,
D2 red flags only, D3 NEWS2 from the kiosk vitals, D4 local LLM alone (--llm). Variants (each measurement at every
threshold +- its error margin) are run with --variants as a robustness check, never in the headline metrics.

    python -m triage.bench.vignettes [--dir ../vignettes] [--variants] [--llm]          (from reasoning_model/src)
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from triage.bench.baselines import d0_always_refer, d3_news2, d4_llm
from triage.bench.metrics import ORD, clopper_pearson, weighted_kappa
from triage.evidence import ROOT, add_answer, add_measurement, add_score, new_record
from triage.rules_engine import bounds, decide, load_config, margin_for
from triage.schema import validate_vignettes

VIGNETTES = ROOT / "vignettes"
RESULTS = ROOT / "results" / "triage"
ALIASES = {"systolic_bp": "sbp", "diastolic_bp": "dbp"}
UNITS = {"heart_rate": ("bpm", "rppg"), "resp_rate": ("/min", "thermal_nostril"),
         "temperature": ("C", "thermal_canthus"), "spo2": ("%", "device"), "sbp": ("mmHg", "device"),
         "dbp": ("mmHg", "device")}
CASE_COLS = {"heart_rate": "hr", "resp_rate": "rr", "temperature": "temp_c", "spo2": "spo2", "sbp": "sbp",
             "dbp": "dbp"}
LEVELS4 = ["URGENT", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE"]


def _yes_no(x):
    return ("yes" if x else "no") if isinstance(x, bool) else x


def normalise(v):
    v = copy.deepcopy(v)
    v["answers"] = {k: _yes_no(a) for k, a in (v.get("answers") or {}).items()}
    for key in ("measurements", "measurements_after_rest", "quality"):
        if v.get(key) is not None:
            v[key] = {ALIASES.get(k, k): x for k, x in v[key].items()}
    v.setdefault("clinician_labels", {})
    return v


def load_vignettes(path=VIGNETTES):
    path = Path(path)
    files = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    out = []
    for f in files:
        vs = [normalise(v) for v in (yaml.safe_load(f.read_text(encoding="utf-8")) or [])]
        errs = validate_vignettes(vs, f.name)
        if errs:
            raise ValueError("invalid vignettes:\n  " + "\n  ".join(errs))
        out += [{**v, "_file": f.name} for v in vs]
    return out


def _readings(x):
    return None if x is None else [float(x), float(x)] if isinstance(x, (int, float)) else [float(r) for r in x]


def to_record(v, cfg, after_rest=False, vitals=True, answers=True):
    rec = new_record(v["id"], cfg, code="vignette")
    ms = (v.get("measurements_after_rest") if after_rest else None) or v["measurements"]
    if vitals:
        for name, x in ms.items():
            reps = _readings(x)
            if name not in UNITS or reps is None:
                continue
            unit, source = UNITS[name]
            add_measurement(rec, name, float(np.mean(reps)), unit, (v.get("quality") or {}).get(name, 0.9), source,
                            None, reps)
    if answers:
        if v.get("age") is not None:
            add_answer(rec, "age", v["age"])
        for item, a in v["answers"].items():
            add_answer(rec, item, a)
        for name, s in (v.get("scores") or {}).items():
            add_score(rec, name, s)
        rec["flags"] = list(v.get("flags") or [])
    if after_rest:
        rec["flags"].append("remeasured")
    return rec


def sys_level(v, cfg, vitals=True, answers=True):
    """-> (final level, rule id, remeasured)."""
    d = decide(to_record(v, cfg, vitals=vitals, answers=answers), cfg)
    if d["level"] != "REMEASURE":
        return d["level"], d["rule_id"], False
    d = decide(to_record(v, cfg, after_rest=True, vitals=vitals, answers=answers), cfg)
    return d["level"], d["rule_id"], True


def red_flags_only_cfg(cfg):
    c = copy.deepcopy(cfg)
    c["ranges"]["required"] = []
    return c


def as_cases(vignettes, cfg):
    """The vignettes as the ED case table the D3 / D4 baselines take."""
    rows = []
    flags = set(cfg["red_flags"]["urgent_items"]) | {"self_harm"}
    for v in vignettes:
        row = {"case_id": v["id"], "o2_device": None,
               "red_flags": [k for k, a in v["answers"].items() if k in flags and a == "yes"],
               "complaint": v.get("narrative") or "not given"}
        for name, col in CASE_COLS.items():
            reps = _readings(v["measurements"].get(name))
            row[col] = float(np.mean(reps)) if reps else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def metrics(levels, labels):
    """§5.2 on vignettes with a consensus label. RETAKE is a level here (the clinicians can label it)."""
    levels, labels = np.asarray(levels, object), np.asarray(labels, object)
    urgent = labels == "URGENT"
    k = int((levels[urgent] == "URGENT").sum())
    out = {"n": len(labels), "urgent_sensitivity": clopper_pearson(k, int(urgent.sum()))}
    ordinal = np.isin(labels, list(ORD)) & np.isin(levels, list(ORD))
    a = np.array([ORD[x] for x in labels[ordinal]])
    b = np.array([ORD[x] for x in levels[ordinal]])
    out["under_triage"] = float(np.mean(b < a)) if len(a) else float("nan")
    out["over_triage"] = float(np.mean(b > a)) if len(a) else float("nan")
    out["weighted_kappa"] = weighted_kappa(a, b) if len(a) else float("nan")
    out["exact_agreement"] = float(np.mean(levels == labels)) if len(labels) else float("nan")
    out["confusion_ref_rows_sys_cols"] = {r: {s: int(((labels == r) & (levels == s)).sum()) for s in LEVELS4 +
                                              ["NOT_SUITABLE", "REMEASURE"]} for r in LEVELS4}
    return out


def inter_rater_kappa(vignettes):
    """Mean pairwise weighted kappa between the raters on the ordinal levels (the ceiling for SYS)."""
    raters = sorted({r for v in vignettes for r in v["clinician_labels"] if r.startswith("rater")})
    ks = []
    for i, r1 in enumerate(raters):
        for r2 in raters[i + 1:]:
            pairs = [(v["clinician_labels"].get(r1), v["clinician_labels"].get(r2)) for v in vignettes]
            pairs = [(ORD[a], ORD[b]) for a, b in pairs if a in ORD and b in ORD]
            if pairs:
                ks.append(weighted_kappa(*map(list, zip(*pairs))))
    return float(np.mean(ks)) if ks else float("nan")


def variants(v, cfg):
    """Every measurement moved to each threshold of its normal and urgent range, -margin and +margin (both
    readings), all else unchanged. For robustness checks only."""
    out = []
    for name, x in v["measurements"].items():
        spec = cfg["ranges"]["measures"].get(name)
        if spec is None or _readings(x) is None:
            continue
        m = margin_for({"name": name, "source": UNITS[name][1]}, cfg)
        for kind in ("normal", "urgent"):
            for side, edge in zip(("low", "high"), bounds(spec[kind])):
                if np.isinf(edge):
                    continue
                for sign in (-1, 1):
                    w = copy.deepcopy(v)
                    val = round(edge + sign * m, 2)
                    w["measurements"][name] = [val, val]
                    w.pop("measurements_after_rest", None)
                    w["id"] = f"{v['id']}~{name}_{kind}_{side}{'+' if sign > 0 else '-'}m"
                    out.append(w)
    return out


def run(vignettes, cfg, with_llm=False):
    rows = []
    rf_cfg = red_flags_only_cfg(cfg)
    for v in vignettes:
        lv, rule, rem = sys_level(v, cfg)
        rows.append({"id": v["id"], "label": v["clinician_labels"].get("consensus"), "SYS": lv, "SYS_rule": rule,
                     "SYS_remeasured": rem, "D1_vitals_only": sys_level(v, cfg, answers=False)[0],
                     "D2_red_flags_only": sys_level(v, rf_cfg, vitals=False)[0]})
    df = pd.DataFrame(rows)
    cases = as_cases(vignettes, cfg)
    df["D0_always_refer"] = d0_always_refer(cases)
    df["D3_news2"] = d3_news2(cases, use=("rr", "hr", "temp_c"))
    if with_llm:
        df["D4_llm"] = d4_llm(cases, vitals=("hr", "rr", "temp_c"))[0]
    return df


def report(df):
    lab = df[df["label"].notna()]
    arms = [c for c in df.columns if c in ("SYS",) or c[:2] in ("D0", "D1", "D2", "D3", "D4")]
    res = {"n_vignettes": len(df), "n_labelled": len(lab), "sys_levels": df["SYS"].value_counts().to_dict(),
           "sys_remeasured": int(df["SYS_remeasured"].sum())}
    if len(lab):
        res["arms"] = {a: metrics(lab[a], lab["label"]) for a in arms}
    return res


def fmt_ci(t):
    return "n/a" if t[0] != t[0] else f"{t[0]:.2f} [{t[1]:.2f}, {t[2]:.2f}]"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(VIGNETTES))
    ap.add_argument("--variants", action="store_true", help="also run the +-margin variants (robustness)")
    ap.add_argument("--llm", action="store_true", help="add D4, the local LLM alone (slow)")
    a = ap.parse_args()
    cfg = load_config()
    vigs = load_vignettes(a.dir)
    df = run(vigs, cfg, a.llm)
    res = report(df)
    res["inter_rater_weighted_kappa"] = inter_rater_kappa(vigs)
    print(f"{res['n_vignettes']} vignettes, {res['n_labelled']} with a clinician consensus label; "
          f"SYS levels {res['sys_levels']}; re-measured {res['sys_remeasured']}")
    if res["n_labelled"]:
        print(f"inter-rater weighted kappa {res['inter_rater_weighted_kappa']:.2f}")
        print(f"{'arm':<20} {'URGENT sens (95% CI)':<24} {'under':>6} {'over':>6} {'kappa':>6} {'exact':>6}")
        for arm, m in res["arms"].items():
            print(f"{arm:<20} {fmt_ci(m['urgent_sensitivity']):<24} {m['under_triage']:6.2f} {m['over_triage']:6.2f} "
                  f"{m['weighted_kappa']:6.2f} {m['exact_agreement']:6.2f}")
    else:
        print("no consensus labels yet: the clinicians label the vignettes (blind to the rules), then metrics appear")
    print(df[["id", "label", "SYS", "SYS_rule", "D1_vitals_only", "D2_red_flags_only", "D3_news2"]].to_string(index=False))
    if a.variants:
        var = [w for v in vigs for w in variants(v, cfg)]
        vdf = run(var, cfg)
        vdf["base"] = vdf["id"].str.split("~").str[0]
        base = dict(zip(df["id"], df["SYS"]))
        changed = (vdf["SYS"] != vdf["base"].map(base)).mean()
        print(f"\nvariants: {len(vdf)}; SYS level differs from the base vignette in {changed:.0%} "
              f"(expected near thresholds)")
        print(vdf.groupby("SYS").size().to_string())
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "vignettes_summary.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
