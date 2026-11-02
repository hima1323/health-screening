"""Reasoning chain, computed by code (never by the LLM). -> record["chain"]

    evidence -> interpretation -> context -> rule -> uncertainty -> advice

Each step points to the evidence IDs (M*, Q*, S*) it rests on. The explainer (P3) may only put this chain into
words; the level, the advice line, the contacts and the disclaimer are copied from here by code.

    python -m triage.reasoning_chain --record <evidence.json>      (from reasoning_model/src)
"""
import argparse
import json
from pathlib import Path

from triage.rules_engine import (answer_equals, bounds, decide, load_config, margin_for, range_for, readings,
                                 reading_status, _answers)


def interpret(m, rec, cfg):
    """One measurement vs its normal and urgent range (with any answer-based adjustment) and error margin."""
    out = {"ref": m["id"], "name": m["name"], "value": m["value"], "unit": m["unit"], "quality": m["quality"],
           "readings": readings(m) if m["value"] is not None else [], "margin": margin_for(m, cfg)}
    if m["value"] is None:
        return {**out, "status": "not_measured"}
    if m["quality"] < cfg["ranges"]["min_quality"]:
        return {**out, "status": "not_usable"}
    normal, adj = range_for(m["name"], "normal", rec, cfg)
    if normal is None:
        return {**out, "status": "no_reference_range"}
    urgent = range_for(m["name"], "urgent", rec, cfg)[0]
    per_reading = [reading_status(v, normal, out["margin"]) for v in out["readings"]]
    worst = max(per_reading, key=["in", "borderline", "out"].index)
    out.update(normal=normal, urgent=urgent, status=worst, reading_status=per_reading,
               confirmed=len(per_reading) >= 2 and all(s == "out" for s in per_reading),
               beyond_urgent=all(not bounds(urgent)[0] <= v <= bounds(urgent)[1] for v in out["readings"]))
    if adj:
        out["range_adjusted"] = {"refs": answer_equals(rec, cfg, adj["when"]["answer"], adj["when"]["equals"])[1],
                                 "note": adj.get("note", "")}
    return out


def context(rec, cfg, interp):
    """Context answers (exercise, caffeine, ...) and what they could explain among the readings that were not 'in'."""
    flagged = {i["name"]: i["ref"] for i in interp if i["status"] in ("borderline", "out")}
    items, ctx = [], cfg["questionnaire"]["sections"]["context"]["items"]
    for item, spec in ctx.items():
        given = _answers(rec, item, include_unconfirmed=True)
        if not given:
            continue
        values = {a["answer"] for a in given}
        entry = {"item": item, "refs": [a["id"] for a in given], "answer": given[-1]["answer"] if len(values) == 1
                 else None}
        if len(values) > 1:
            entry["note"] = "conflicting answers: not used to relax any rule"
        elif not all(a["confirmed"] for a in given):
            entry["note"] = "answer not confirmed: not used to relax any rule"
        elif entry["answer"] == "yes":
            entry["effect"] = spec["effect"]
            entry["could_explain"] = [flagged[n] for n in spec.get("explains", []) if n in flagged]
        items.append(entry)
    return items


def uncertainty(rec, cfg, interp, ctx, decision):
    u = []
    for c in ctx:
        if c.get("could_explain"):
            u.append({"kind": "possible_explanation", "refs": c["refs"] + c["could_explain"], "text": c["effect"]})
        if c.get("note"):
            u.append({"kind": "unclear_answer", "refs": c["refs"], "text": c["note"]})
    for i in interp:
        if i["status"] == "borderline":
            u.append({"kind": "borderline", "refs": [i["ref"]],
                      "text": f"{i['name']} is outside the range by no more than the measurement error"})
        elif i["status"] in ("out", "borderline") and not i.get("confirmed"):
            u.append({"kind": "unconfirmed", "refs": [i["ref"]],
                      "text": f"{i['name']} was outside the range on only some readings"})
        if i["status"] == "not_usable":
            u.append({"kind": "low_quality", "refs": [i["ref"]], "text": f"{i['name']} reading was not clear enough"})
    measured = {m["name"] for m in rec["measurements"] if m["value"] is not None}
    missing = [(n, s["measured_by"]) for n, s in cfg["ranges"]["measures"].items() if n not in measured]
    if missing:
        u.append({"kind": "not_measured", "refs": [], "names": [n for n, _ in missing],
                  "text": "not measured by this check" + (" (needs a separate device)"
                                                           if all(b == "device" for _, b in missing) else "")})
    asked = {s["name"] for s in rec["scores"]}
    not_asked = [s for s in cfg["questionnaire"]["scores"] if s not in asked]
    if not_asked:
        u.append({"kind": "not_asked", "refs": [], "names": not_asked, "text": "questions not answered"})
    if cfg["ranges"]["error_margins"].get("status") != "measured":
        u.append({"kind": "margins_placeholder", "refs": [], "text": "device error margins are not yet measured"})
    if decision["rules_status"] != "approved":
        u.append({"kind": "rules_draft", "refs": [], "text": "rules are a draft, not yet reviewed by a clinician"})
    return u


def advice(cfg, decision):
    r = cfg["rules"]
    text = r["wording"][decision["wording_key"]] if decision["wording_key"] else r["advice"][decision["level"]]
    contacts = []
    if "show_crisis_contacts" in decision["actions"]:
        contacts += cfg["contacts"]["crisis"]
    if decision["level"] == "URGENT" or contacts:
        contacts = cfg["contacts"]["emergency"] + contacts
    return {"level": decision["level"], "text": text, "contacts": contacts,
            "contacts_verified": bool(cfg["contacts"].get("verified")), "disclaimer": r["disclaimer"]}


def build_chain(rec, decision, cfg):
    interp = [interpret(m, rec, cfg) for m in rec["measurements"]]
    ctx = context(rec, cfg, interp)
    return [
        {"step": "evidence", "measurements": [m["id"] for m in rec["measurements"]],
         "answers": [a["id"] for a in rec["answers"]], "scores": [s["id"] for s in rec["scores"]],
         "flags": list(rec["flags"])},
        {"step": "interpretation", "items": interp},
        {"step": "context", "items": ctx},
        {"step": "rule", "rule_id": decision["rule_id"], "level": decision["level"], "reason": decision["reason"],
         "refs": decision["refs"], "also_matched": [m["rule_id"] for m in decision["also_matched"]]},
        {"step": "uncertainty", "items": uncertainty(rec, cfg, interp, ctx, decision)},
        {"step": "advice", **advice(cfg, decision)},
    ]


def apply(rec, cfg):
    """Decide and reason in one go; fills record['decision'] and record['chain'] and returns the record."""
    rec["decision"] = decide(rec, cfg)
    rec["chain"] = build_chain(rec, rec["decision"], cfg)
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True, help="evidence record JSON file")
    rec = json.loads(Path(ap.parse_args().record).read_text(encoding="utf-8"))
    print(json.dumps(apply(rec, load_config()), indent=1))
