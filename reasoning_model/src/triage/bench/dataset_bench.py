"""Benchmark the expert system on a sample dataset you provide (CSV or Excel, one row per case / person).

No live kiosk input is needed: each row is turned into an evidence record and run through the same rule engine
(with one REMEASURE round), next to the baselines D0 always refer, D1 vitals only, D2 red flags only, D3 NEWS2 and
optionally D4 the local LLM alone. With a reference column the decision metrics are computed (URGENT sensitivity with
an exact 95% CI, under- / over-triage, weighted kappa, confusion matrix); without one, the level distribution only.

Columns (names are matched case-insensitively; every column is optional except one id and at least one vital or
answer; see templates/benchmark_dataset_template.csv):
  id                      case_id | id | patient_id
  vitals                  heart_rate|hr|pulse, resp_rate|rr, temperature|temp_c|temp (deg F converted when > 50),
                          spo2|o2sat, sbp|systolic_bp, dbp|diastolic_bp. A second reading in <name>_2 (e.g. hr_2);
                          one reading only = treated as two equal readings (the repeat agrees).
  vitals after rest       <name>_rest (e.g. hr_rest): used if the system asks for a REMEASURE (default: same values)
  quality                 quality_<name> (0-1, default 0.9)
  answers                 any questionnaire / red-flag item id as a column: chest_pain, severe_breathlessness,
                          fainting, stroke_signs, confusion, worst_headache, severe_bleeding, severe_allergy,
                          self_harm, exercise_last_30min, caffeine_last_2h, feeling_unwell, fever_feeling, athlete,
                          pregnant, symptom_duration_days; yes/no, 1/0, true/false
  age                     age (years)
  scores                  phq2, gad2 (0-6)
  chief complaint         complaint | chief_complaint: mapped to red flags with red_flags.yaml when no red-flag
                          columns are given
  reference (optional)    expected_level | label (URGENT / SEE_DOCTOR_SOON / SELF_CARE / RETAKE / NOT_SUITABLE), or
                          esi (+ admitted): ESI 1-2 = URGENT, ESI 3 or admitted = SEE_DOCTOR_SOON, else SELF_CARE

    python -m triage.bench.dataset_bench <file.csv|.xlsx> [--name NAME] [--llm] [--explain 5]   (from reasoning_model/src)

Outputs in results/triage/dataset_<NAME>/: cases.csv (per-case levels and rules), summary.json, REPORT.md.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from triage.bench.ed_cases import complaint_patterns, map_complaint
from triage.bench.vignettes import fmt_ci, normalise, report, run, to_record
from triage.evidence import ROOT
from triage.explainer import explain
from triage.reasoning_chain import apply
from triage.rules_engine import load_config

VITALS = {"heart_rate": ["heart_rate", "hr", "pulse"], "resp_rate": ["resp_rate", "rr"],
          "temperature": ["temperature", "temp_c", "temp"], "spo2": ["spo2", "o2sat"],
          "sbp": ["sbp", "systolic_bp"], "dbp": ["dbp", "diastolic_bp"]}
ID_COLS = ["case_id", "id", "patient_id"]
YES = {"yes", "y", "1", "true", "t"}
NO = {"no", "n", "0", "false", "f"}
LEVELS = {"URGENT", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE", "NOT_SUITABLE"}


def read(path):
    path = Path(path)
    df = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)
    df.columns = [re.sub(r"\W+", "_", str(c).strip().lower()) for c in df.columns]
    return df


def _num(x):
    try:
        v = float(x)
        return None if np.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _col(df, names):
    return next((n for n in names if n in df.columns), None)


def _answer(x):
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    s = str(x).strip().lower()
    if s in YES:
        return "yes"
    if s in NO:
        return "no"
    v = _num(x)
    return None if s in ("", "nan", "none") else (v if v is not None else s)


def reference(row):
    lab = row.get("expected_level", row.get("label"))
    if isinstance(lab, str) and lab.strip().upper() in LEVELS:
        return lab.strip().upper()
    esi = _num(row.get("esi"))
    if esi is None:
        return None
    admitted = _answer(row.get("admitted")) == "yes"
    return "URGENT" if esi <= 2 else "SEE_DOCTOR_SOON" if esi == 3 or admitted else "SELF_CARE"


def to_vignettes(df, cfg):
    """Each row -> the vignette format (vignettes.py), so the same runner, baselines and metrics are used."""
    idc = _col(df, ID_COLS)
    items = set(cfg["red_flags"]["items"]) | {i for s in cfg["questionnaire"]["sections"].values()
                                             if isinstance(s["items"], dict) for i in s["items"]}
    items -= {"consent", "age"}
    flag_cols = [c for c in df.columns if c in cfg["red_flags"]["items"]]
    complaint = _col(df, ["complaint", "chief_complaint", "chiefcomplaint"])
    pats = complaint_patterns(cfg)
    temp_col = _col(df, VITALS["temperature"])
    out, used = [], set()
    for i, row in enumerate(df.to_dict("records")):
        v = {"id": str(row[idc]) if idc else f"row{i + 1}", "measurements": {}, "measurements_after_rest": {},
             "quality": {}, "answers": {}, "scores": {}, "clinician_labels": {"consensus": reference(row)}}
        for name, aliases in VITALS.items():
            c = _col(df, aliases)
            if not c:
                continue
            used.add(name)
            r1, r2, rest = _num(row.get(c)), _num(row.get(f"{c}_2")), _num(row.get(f"{c}_rest"))
            if name == "temperature" and c == temp_col:
                r1, r2, rest = [(x - 32) * 5 / 9 if x is not None and x > 50 else x for x in (r1, r2, rest)]
            if r1 is not None:
                v["measurements"][name] = [r1, r2 if r2 is not None else r1]
                v["measurements_after_rest"][name] = [rest, rest] if rest is not None else v["measurements"][name]
            q = _num(row.get(f"quality_{c}", row.get(f"quality_{name}")))
            if q is not None:
                v["quality"][name] = q
        for c in df.columns:
            if c in items:
                a = _answer(row[c])
                if a is not None:
                    v["answers"][c] = a
        if not flag_cols and complaint:
            for it in map_complaint(row.get(complaint), pats):
                v["answers"][it] = "yes"
            for it in cfg["red_flags"]["urgent_items"] + ["self_harm"]:
                v["answers"].setdefault(it, "no")
        if (age := _num(row.get("age"))) is not None:
            v["age"] = age
        for s in ("phq2", "gad2"):
            if (x := _num(row.get(s))) is not None:
                v["scores"][s.upper()] = x
        if complaint:
            v["narrative"] = str(row.get(complaint) or "")
        out.append(normalise(v))
    return out, sorted(used)


def explain_examples(vigs, df_res, cfg, k, use_llm):
    """Explanation cards for the first k cases of each level (shows what a person would read)."""
    cards = []
    for lv in ("URGENT", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE", "NOT_SUITABLE"):
        for vid in df_res.loc[df_res["SYS"] == lv, "id"].head(k):
            v = next(x for x in vigs if x["id"] == vid)
            rec = apply(to_record(v, cfg), cfg)
            if rec["decision"]["level"] == "REMEASURE":           # the final card, after the second measurement
                rec = apply(to_record(v, cfg, after_rest=True), cfg)
            card, log = explain(rec, cfg, use_llm=use_llm)
            cards.append({"id": vid, "level": lv, "summary": card["summary"], "reasons": card["reasons"],
                          "advice": card["advice"], "text_source": log["source"]})
    return cards


def write_report(name, res, df_res, cards, cols, out):
    md = [f"# Expert-system benchmark on `{name}`", "",
          f"{res['n_vignettes']} cases; vitals present: {', '.join(cols) or 'none'}; "
          f"{res['n_labelled']} with a reference level.", "",
          f"System levels: {res['sys_levels']} (re-measured once: {res['sys_remeasured']})", ""]
    if res["n_labelled"]:
        md += ["| arm | URGENT sensitivity (95% CI) | under-triage | over-triage | weighted kappa | exact agreement |",
               "|---|---|---|---|---|---|"]
        for arm, m in res["arms"].items():
            md.append(f"| {arm} | {fmt_ci(m['urgent_sensitivity'])} | {m['under_triage']:.2f} | "
                      f"{m['over_triage']:.2f} | {m['weighted_kappa']:.2f} | {m['exact_agreement']:.2f} |")
        cm = res["arms"]["SYS"]["confusion_ref_rows_sys_cols"]
        cols4 = list(next(iter(cm.values())))
        md += ["", "Confusion matrix, SYS (rows = reference, columns = system):", "",
               "| reference \\ system | " + " | ".join(cols4) + " |", "|---" * (len(cols4) + 1) + "|"]
        md += [f"| {r} | " + " | ".join(str(cm[r][c]) for c in cols4) + " |" for r in cm]
    rules = df_res["SYS_rule"].value_counts()
    md += ["", "Rules that set the level: " + ", ".join(f"{k} {v}" for k, v in rules.items())]
    if cards:
        md += ["", "## Example result cards", ""]
        for c in cards:
            md += [f"**{c['id']} - {c['level']}** ({c['text_source']}): {c['summary']}  ",
                   "".join(f"- {r}  \n" for r in c["reasons"]) + f"Advice: {c['advice']}", ""]
    md += ["Rules, ranges and wording are DRAFTS (not clinician-approved); error margins are placeholders. "
           "Research prototype, not a medical device."]
    (out / "REPORT.md").write_text("\n".join(md), encoding="utf-8")
    return "\n".join(md)


def main(a):
    cfg = load_config()
    df = read(a.file)
    vigs, cols = to_vignettes(df, cfg)
    df_res = run(vigs, cfg, with_llm=a.llm)
    res = report(df_res)
    name = a.name or Path(a.file).stem
    out = ROOT / "results" / "triage" / f"dataset_{name}"
    out.mkdir(parents=True, exist_ok=True)
    df_res.to_csv(out / "cases.csv", index=False)
    cards = explain_examples(vigs, df_res, cfg, a.explain, a.llm_explain) if a.explain else []
    (out / "summary.json").write_text(json.dumps({**res, "examples": cards}, indent=1, default=str), encoding="utf-8")
    print(write_report(name, res, df_res, cards, cols, out))
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--name")
    ap.add_argument("--llm", action="store_true", help="add D4, the local LLM deciding alone (slow)")
    ap.add_argument("--explain", type=int, default=2, help="example cards per level (0 = none)")
    ap.add_argument("--llm-explain", action="store_true", help="write the example cards with the local LLM")
    main(ap.parse_args())
