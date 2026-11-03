"""E1.1 source check: every number in vital_ranges.yaml, every row of evidence/evidence_table.csv and the PHQ-2 / GAD-2
wording, each to be checked against the official current document (NEWS2 chart, ESI handbook, NICE NG253, the
official PHQ / GAD distribution).

This script builds and maintains evidence/source_check.csv. A person fills, per row: source_document,
document_version, page_or_section, exact_source_value, checked_by, checked_date. Re-running keeps what was filled,
adds new rows and recomputes `match` (the source wins: every mismatch is listed for the clinician). Opening the
documents is a human step; nothing is downloaded here.

    python -m triage.derive.source_check          (from reasoning_model/src)
"""
import csv

from triage.evidence import ROOT
from triage.rules_engine import load_config

OUT = ROOT / "evidence" / "source_check.csv"
FILLED = ["source_document", "document_version", "page_or_section", "exact_source_value", "checked_by",
          "checked_date", "note"]
COLUMNS = ["item", "kind", "starter_kit_value", "how_to_compare", "cited_sources"] + FILLED + ["match"]
INCLUSIVE = ("the range [low, high] is inclusive: a value counts as outside at low - 1 / high + 1 (one decimal for "
             "temperature). Example: NEWS2 'pulse <= 40 scores 3' = urgent.low 41. Enter the source value converted "
             "the same way, and the source's own wording in note")
WHERE = {"heart_rate": "NEWS2 chart (RCP 2017) pulse bands; ESI handbook danger zone", "resp_rate": "NEWS2 chart RR "
         "bands; ESI danger zone", "temperature": "NEWS2 chart temperature bands", "spo2": "NEWS2 SpO2 scale 1; ESI "
         "danger zone", "sbp": "NEWS2 systolic bands; national hypertension guideline", "dbp": "national hypertension "
         "guideline"}


def rows(cfg):
    out = []
    for name, spec in cfg["ranges"]["measures"].items():
        cited = "; ".join(spec.get("sources", [])) or WHERE.get(name, "")
        for kind in ("normal", "urgent"):
            for side, v in zip(("low", "high"), spec[kind]):
                if v is not None:
                    out.append({"item": f"{name}.{kind}.{side}", "kind": "threshold", "starter_kit_value": v,
                                "how_to_compare": INCLUSIVE, "cited_sources": cited})
        for adj in spec.get("adjust", []):
            out.append({"item": f"{name}.normal.adjusted_if_{adj['when']['answer']}", "kind": "threshold",
                        "starter_kit_value": adj.get("normal"), "cited_sources": adj.get("note", "")})
        if "fever" in spec:
            out.append({"item": f"{name}.fever", "kind": "threshold", "starter_kit_value": spec["fever"],
                        "cited_sources": cited})
    out.append({"item": "min_quality", "kind": "threshold", "starter_kit_value": cfg["ranges"]["min_quality"],
                "cited_sources": "own choice (measurement benchmark E5)"})
    for item in ("phq2_1", "phq2_2", "gad2_1", "gad2_2"):
        q = cfg["questionnaire"]["sections"]["mood"]["items"][item]["question"]
        out.append({"item": f"questionnaire.{item}", "kind": "exact_wording", "starter_kit_value": q,
                    "cited_sources": "official PHQ / GAD distribution (Pfizer); check the terms of use"})
    with open(ROOT / "evidence" / "evidence_table.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({"item": f"evidence.{r['condition']}", "kind": "evidence_row",
                        "starter_kit_value": r["threshold_or_content"], "cited_sources": f"{r['source']} {r['doi_or_url']}"})
    return out


def _same(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return " ".join(str(a).lower().split()) == " ".join(str(b).lower().split())


def build(cfg=None, path=OUT):
    cfg = cfg or load_config()
    old = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            old = {r["item"]: r for r in csv.DictReader(f)}
    table = []
    for r in rows(cfg):
        prev = old.get(r["item"], {})
        r.update({k: prev.get(k, "") for k in FILLED})
        src = r["exact_source_value"]
        r.setdefault("how_to_compare", "exact value / exact wording")
        r["match"] = "" if not src else ("yes" if _same(src, r["starter_kit_value"]) else "MISMATCH")
        table.append(r)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(table)
    return table


if __name__ == "__main__":
    t = build()
    done = [r for r in t if r["exact_source_value"]]
    bad = [r for r in t if r["match"] == "MISMATCH"]
    print(f"{OUT.relative_to(ROOT)}: {len(t)} rows, {len(done)} checked against a source, {len(bad)} mismatches")
    for r in bad:
        print(f"  MISMATCH {r['item']}: starter kit {r['starter_kit_value']} vs source {r['exact_source_value']} "
              f"({r['source_document']} {r['page_or_section']})")
    if len(done) < len(t):
        print("fill source_document, document_version, page_or_section, exact_source_value, checked_by, checked_date "
              "for the remaining rows from the official documents, then re-run")
