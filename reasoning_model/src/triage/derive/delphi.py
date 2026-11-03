"""E1.5 Delphi consensus pack and scoring.

  python -m triage.derive.delphi --round 1                 -> results/triage/delphi_round1.xlsx
  python -m triage.derive.delphi --score <filled xlsx>...  -> per-rule agreement across the clinicians' forms

Round pack (columns of templates/delphi_round_form.csv): one row per rule with its plain-text condition, level, the
cited sources, a data-check summary (E1.2 MIMIC dev, E1.3 NHANES, E1.4 rule learning, from results/triage/derive/
when they exist) and empty rating / suggested_change / comment columns. 3-5 clinicians rate independently.
Scoring: a rule is kept when >= 80% rate it `agree`; `modify` rules are rewritten and go to the next round with the
anonymous group results; stop after round 2 or 3. Each rule's history then goes into its provenance card
(templates/rule_provenance_card.yaml) under `provenance:` in rules.yaml.
"""
import argparse
import json
from collections import Counter

import pandas as pd

from triage.evidence import ROOT
from triage.rules_engine import load_config, rule_table

DERIVE = ROOT / "results" / "triage" / "derive"
OUT = ROOT / "results" / "triage"
KEEP = 0.8
COLUMNS = ["rule_id", "level", "rule_text", "sources", "data_check_summary", "rule_learning_suggestion",
           "rating(agree/modify/remove)", "suggested_change", "comment"]
RULE_SOURCES = {"R01_red_flag": "red_flags", "R02_self_harm": "red_flags", "R07_mood_screen": "PHQ-2: Kroenke 2003, "
                "Levis 2020 JAMA (>=3: sens 0.72, spec 0.85); GAD-2: Kroenke 2007, Plummer 2016",
                "R00_out_of_scope": "vital_ranges.yaml population (starter kit)"}


def _load(name):
    p = DERIVE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def data_check(rule_id, cfg, mimic, nhanes):
    if rule_id in ("R05_vital_far_out", "R06_vital_out", "R06a_fever_unwell") and mimic:
        kind = "urgent" if rule_id == "R05_vital_far_out" else "normal"
        parts = []
        for name, rows in mimic["cutoffs"].items():
            for r in rows:
                if r["cutoff"].startswith(kind) and r["n_urgent"]:
                    parts.append(f"{name} {r['cutoff']}: sens {r['sensitivity']:.2f}, FPR "
                                 f"{r['false_positive_rate']:.2f} (with kiosk error {r['sensitivity_with_kiosk_error']:.2f}"
                                 f" / {r['fpr_with_kiosk_error']:.2f})")
        txt = f"MIMIC dev (n={mimic['n_visits_dev']}): " + "; ".join(parts)
        if nhanes:
            flagged = [f"{r['measure']} {r['cutoff']}: {100 * r['weighted_share_flagged']:.1f}% of healthy adults"
                       for r in nhanes if r["group"] == "all" and r["cutoff"].startswith(kind)]
            txt += " | NHANES over-referral: " + "; ".join(flagged)
        return txt
    if rule_id == "R01_red_flag" and mimic:
        rf = mimic["red_flags"]
        return (f"MIMIC dev: {100 * rf['urgent_no_red_flag_and_normal_kiosk_vitals']:.0f}% of urgent visits had no red "
                f"flag and normal kiosk vitals; {100 * rf['unmapped_complaint_share']:.0f}% of complaints map to no red "
                "flag (see mimic_dev_red_flags.csv)")
    return "n/a" if rule_id in ("R07_mood_screen", "R99_default", "R00_out_of_scope") else "<fill from E1.2-E1.4>"


def sources(rule_id, cfg):
    s = RULE_SOURCES.get(rule_id)
    if s == "red_flags":
        return "; ".join(cfg["red_flags"].get("sources", []))
    if s:
        return s
    if rule_id.startswith(("R05", "R06")):
        return "; ".join(sorted({x for m in cfg["ranges"]["measures"].values() for x in m.get("sources", [])}))
    return ""


def build_round(rnd, cfg):
    mimic, nhanes, rl = _load("mimic_dev_summary.json"), _load("nhanes_overreferral.json"), _load("rule_learning.json")
    sugg = (f"depth-3 tree on {rl['source']}: sens {rl['tree_depth3']['sensitivity_dev']:.2f} / spec "
            f"{rl['tree_depth3']['specificity_dev']:.2f} vs draft {rl['draft_rules_urgent']['sensitivity']:.2f} / "
            f"{rl['draft_rules_urgent']['specificity']:.2f}; see rule_learning.json for the splits") if rl else ""
    rows = []
    for r in rule_table(cfg):
        rows.append({"rule_id": r["id"], "level": r["level"], "rule_text": r["when"], "sources": sources(r["id"], cfg),
                     "data_check_summary": data_check(r["id"], cfg, mimic, nhanes),
                     "rule_learning_suggestion": sugg if r["id"] in ("R05_vital_far_out", "R06_vital_out") else "",
                     "rating(agree/modify/remove)": "", "suggested_change": "", "comment": ""})
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"delphi_round{rnd}.xlsx"
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame(rows, columns=COLUMNS).to_excel(xw, sheet_name="rules", index=False)
        pd.DataFrame({"instructions": [
            f"Delphi round {rnd}. Rate each rule independently: agree, modify (write the change) or remove.",
            f"A rule is kept when >= {int(KEEP * 100)}% of the panel agree; 'modify' rules go to the next round.",
            "The data-check numbers are from development data only and include a simulated kiosk measurement error.",
            f"Rules version {cfg['rules']['version']} ({cfg['rules']['status']})."]}).to_excel(xw, sheet_name="read_me",
                                                                                             index=False)
    return path


def score(paths):
    votes = {}
    for p in paths:
        df = pd.read_excel(p, sheet_name="rules")
        for _, r in df.iterrows():
            v = str(r["rating(agree/modify/remove)"]).strip().lower()
            if v in ("agree", "modify", "remove"):
                votes.setdefault(r["rule_id"], []).append(v)
    out = []
    for rid, vs in votes.items():
        c = Counter(vs)
        share = c["agree"] / len(vs)
        out.append({"rule_id": rid, "n_raters": len(vs), **c, "agree_share": round(share, 2),
                    "decision": "keep" if share >= KEEP else "remove?" if c["remove"] > c["modify"] else
                    "modify -> next round"})
    return pd.DataFrame(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int)
    ap.add_argument("--score", nargs="+", help="the clinicians' filled forms")
    a = ap.parse_args()
    if a.score:
        print(score(a.score).to_string(index=False))
    else:
        print(build_round(a.round or 1, load_config()))
