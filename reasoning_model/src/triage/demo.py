"""Run sample kiosk sessions through evidence -> rule engine -> reasoning chain and print a result card for each.

The sessions are synthetic. The wording on the card comes from the reasoning chain (code); the LLM explainer is P3.

    python -m triage.demo [--json]          (from reasoning_model/src)
"""
import argparse
import copy
import json

from triage.evidence import add_answer, add_measurement, add_score, by_id, new_record
from triage.reasoning_chain import apply
from triage.rules_engine import load_config

NO = ["chest_pain", "severe_breathlessness", "fainting", "confusion", "stroke_signs", "worst_headache",
      "severe_bleeding", "severe_allergy", "self_harm", "exercise_last_30min", "caffeine_last_2h", "feeling_unwell", "athlete"]
SAMPLES = [
    ("Healthy adult, everything normal",
     {"heart_rate": [72, 74], "resp_rate": [14, 15], "temperature": [36.7, 36.6]}, {}, {"PHQ2": 0, "GAD2": 1}),
    ("Raised heart rate after coffee",
     {"heart_rate": [109, 107], "resp_rate": [16, 16], "temperature": [36.9, 36.9]}, {"caffeine_last_2h": "yes"},
     {"PHQ2": 1, "GAD2": 2}),
    ("Chest pain with normal vitals",
     {"heart_rate": [78, 80], "resp_rate": [16, 17], "temperature": [36.8, 36.8]}, {"chest_pain": "yes"},
     {"PHQ2": 0, "GAD2": 0}),
    ("High fever and fast breathing",
     {"heart_rate": [118, 121], "resp_rate": [26, 27], "temperature": [39.6, 39.5]}, {"feeling_unwell": "yes"},
     {"PHQ2": 1, "GAD2": 0}),
    ("Just ran up the stairs (borderline -> re-measure -> decision)",
     {"heart_rate": [104, 106], "resp_rate": [19, 20], "temperature": [36.9, 37.0]}, {"exercise_last_30min": "yes"},
     {"PHQ2": 0, "GAD2": 0}, {"heart_rate": [80, 78], "resp_rate": [15, 15], "temperature": [36.8, 36.8]}),
    ("Low mood and worry scores",
     {"heart_rate": [70, 71], "resp_rate": [14, 14], "temperature": [36.6, 36.6]}, {}, {"PHQ2": 4, "GAD2": 3}),
    ("Self-harm thoughts reported",
     {"heart_rate": [88, 90], "resp_rate": [16, 16], "temperature": [36.7, 36.7]}, {"self_harm": "yes"},
     {"PHQ2": 5, "GAD2": 4}),
    ("Camera could not get a clear reading",
     {"heart_rate": [None, None], "resp_rate": [15, 15], "temperature": [36.7, 36.7]}, {}, {"PHQ2": 0, "GAD2": 0}),
]
UNITS = {"heart_rate": ("bpm", "rppg"), "resp_rate": ("/min", "thermal_nostril"),
         "temperature": ("C", "thermal_canthus")}


def session(cfg, vitals, answers, scores):
    rec = new_record("demo", cfg, code="demo")
    for name, reps in vitals.items():
        unit, source = UNITS[name]
        if reps[0] is None:
            add_measurement(rec, name, None, unit, 0.1, source)
        else:
            add_measurement(rec, name, round(sum(reps) / len(reps), 1), unit, 0.9, source, None, reps)
    for item in NO:
        add_answer(rec, item, answers.get(item, "no"))
    for name, v in scores.items():
        add_score(rec, name, v)
    return rec


def remeasure(rec, vitals):
    rec = copy.deepcopy(rec)
    for m in rec["measurements"]:
        if m["name"] in vitals:
            m["repeat_values"] = vitals[m["name"]]
            m["value"] = round(sum(vitals[m["name"]]) / len(vitals[m["name"]]), 1)
    rec["flags"].append("remeasured")
    return rec


def sample_records(cfg):
    """[(title, decided record)] for every sample, including the decision after a REMEASURE."""
    out = []
    for title, vitals, answers, scores, *again in SAMPLES:
        rec = apply(session(cfg, vitals, answers, scores), cfg)
        out.append((title, rec))
        if again and rec["decision"]["level"] == "REMEASURE":
            out.append((title + ": after the second measurement", apply(remeasure(rec, again[0]), cfg)))
    return out


def card(title, rec):
    ch = {s["step"]: s for s in rec["chain"]}
    ids = by_id(rec)
    adv, rule = ch["advice"], ch["rule"]
    out = [f"  LEVEL: {adv['level']}   (rule {rule['rule_id']})", f"  Advice: {adv['text']}",
           f"  Why: {rule['reason']}"]
    cited = [ids[r] for r in rule["refs"]]
    if cited:
        out.append("  Based on: " + "; ".join(
            f"{x['id']} {x['name']} {x.get('repeat_values', x['value'])} {x['unit']}" if "name" in x and "unit" in x
            else f"{x['id']} {x.get('item', x.get('name'))} = {x.get('answer', x.get('value'))}" for x in cited))
    readings = [f"{i['name']} {i['readings']} vs normal {i['normal']} -> {i['status']}"
                if "normal" in i else f"{i['name']}: {i['status']}" for i in ch["interpretation"]["items"]]
    out.append("  Readings: " + " | ".join(readings))
    ctx = [f"{c['item']}={c['answer']}" for c in ch["context"]["items"] if c.get("answer") == "yes"]
    if ctx:
        out.append("  Context: " + ", ".join(ctx))
    unc = [u["text"] for u in ch["uncertainty"]["items"] if u["kind"] not in ("rules_draft", "margins_placeholder",
                                                                               "not_measured")]
    if unc:
        out.append("  Uncertainty: " + "; ".join(unc))
    if adv["contacts"]:
        out.append("  Contacts: " + ", ".join(f"{c['name']} {c['number']}" for c in adv["contacts"])
                   + ("" if adv["contacts_verified"] else "  [numbers not yet verified]"))
    out.append(f"  {adv['disclaimer']}")
    return f"\n=== {title} ===\n" + "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="also print the full evidence record + chain of each")
    a = ap.parse_args()
    cfg = load_config()
    print(f"Rules {cfg['rules']['version']} ({cfg['rules']['status']}: not clinician-reviewed); "
          f"error margins {cfg['ranges']['error_margins']['status']}.")
    for title, vitals, answers, scores, *again in SAMPLES:
        rec = apply(session(cfg, vitals, answers, scores), cfg)
        print(card(title, rec))
        if again and rec["decision"]["level"] == "REMEASURE":
            rec = apply(remeasure(rec, again[0]), cfg)
            print(card(title + ": after 5 min rest and a second measurement", rec))
        if a.json:
            print(json.dumps(rec, indent=1))
