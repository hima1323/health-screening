"""Explainer (starter kit phase E4): one local Ollama call (temperature 0, JSON schema) that puts record["chain"] into
plain words, then the verifier; one retry with the verifier's errors, else the deterministic template.

The LLM sees the chain with every number replaced by a placeholder ({M1.value}, {M1.unit}) and must write none
itself. Code then fills the placeholders from the record and assembles the card: the level label, the fixed advice
line, the contacts and the disclaimer are never written by the LLM. render_template() is always complete and always
passes the verifier, so the card never depends on the LLM being available.

    python -m triage.explainer --demo [--no-llm]          (from reasoning_model/src): explain the demo sessions
"""
import argparse
import json
import re
import time

from triage.evidence import by_id
from triage.llm import LLMError, chat_json, load_llm_config
from triage.rules_engine import bounds
from triage.verify import verify_card, verify_explanation

LABELS = {"URGENT": "URGENT: get medical help now", "SEE_DOCTOR_SOON": "SEE A DOCTOR SOON",
          "SELF_CARE": "SELF-CARE & MONITOR", "RETAKE": "RETAKE THE MEASUREMENT",
          "REMEASURE": "REST 5 MINUTES, THEN MEASURE AGAIN", "NOT_SUITABLE": "THIS CHECK IS NOT SUITABLE FOR YOU"}
SCORES = {"PHQ2": "how often you were bothered by little interest or feeling down",
          "GAD2": "how often you were bothered by feeling nervous or not being able to stop worrying"}
LLM_LEVELS = {"URGENT": "urgent: get medical help now", "SEE_DOCTOR_SOON": "see a doctor soon",
              "SELF_CARE": "self-care and monitor", "RETAKE": "retake the measurement",
              "REMEASURE": "rest for a few minutes, then measure again", "NOT_SUITABLE": "this check is not suitable"}
NAMES = {"heart_rate": "heart rate", "resp_rate": "breathing rate", "temperature": "temperature",
         "spo2": "oxygen level", "sbp": "blood pressure (top number)", "dbp": "blood pressure (bottom number)"}
WORDS = {**NAMES, "PHQ2": "mood questions", "GAD2": "worry questions"}     # digit-free names for the template
SCHEMA = {"type": "object", "required": ["summary", "reasons", "uncertainty", "next_step"],
          "properties": {"summary": {"type": "string"},
                         "reasons": {"type": "array", "items": {"type": "object", "required": ["id", "text"],
                                                                "properties": {"id": {"type": "string"},
                                                                               "text": {"type": "string"}}}},
                         "uncertainty": {"type": "string"}, "next_step": {"type": "string"}}}
SYSTEM = """You explain the result of a health kiosk check to a member of the public, in plain, calm English.
The decision has ALREADY been made by fixed rules; you only explain the reasoning you are given. Do not change it.
Rules for your reply:
- Reply with JSON: summary (one or two sentences), reasons (a list of {id, text}), uncertainty, next_step.
- reasons: one entry for the deciding rule (use its rule id as id) and one per finding that matters (use its ref).
- Write NO numbers at all. To mention a reading, write its placeholder exactly, e.g. "{M1.value} {M1.unit}".
- Do not name any illness or condition, do not mention medicines or doses, do not reassure that a doctor is not
  needed, and do not use the words of a different result level.
- next_step: one short sentence on what to do now. Do not copy the advice line: code shows it separately.
- Short sentences. Speak to the person as "you"."""


def direction(item):
    lo, hi = bounds(item["normal"])
    return "above" if item["value"] > hi else "below" if item["value"] < lo else "within"


def facts(rec, cfg):
    """The chain as the LLM sees it: words and placeholders only."""
    chain = {s["step"]: s for s in rec["chain"]}
    d = rec["decision"]
    findings = []
    for i in chain["interpretation"]["items"]:
        f = {"ref": i["ref"], "measure": NAMES.get(i["name"], i["name"]), "reading": f"{{{i['ref']}.value}} "
             f"{{{i['ref']}.unit}}", "status": i["status"]}
        if i["status"] in ("in", "borderline", "out"):
            f["compared_with_usual_range"] = direction(i)
            f["confirmed_on_repeat"] = bool(i.get("confirmed"))
        if i.get("range_adjusted"):
            f["range_adjusted_because"] = i["range_adjusted"]["note"]
        findings.append(f)
    answers = by_id(rec)
    return {"result_level": LLM_LEVELS[d["level"]],
            "deciding_rule": {"id": d["rule_id"], "reason": d["reason"],
                              "based_on": [r for r in d["refs"] if r in answers]},
            "other_rules_that_also_matched": [m["rule_id"] for m in d["also_matched"]],
            "findings": findings,
            "context": [{"item": re.sub(r"_last_\w+$", " recently", c["item"]).replace("_", " "), "answer": c["answer"],
                         **({"effect": c["effect"]} if c.get("effect") else {}),
                         **({"note": c["note"]} if c.get("note") else {})} for c in chain["context"]["items"]],
            "question_scores": [{"ref": x["id"], "score": SCORES.get(x["name"], x["name"]),
                                 "at_or_above_cutoff": x["value"] >= cfg["questionnaire"]["scores"][x["name"]]["cutoff"]}
                                for x in rec["scores"] if x["name"] in cfg["questionnaire"]["scores"]],
            "uncertainty": [u["text"] for u in chain["uncertainty"]["items"]]}


def fill(text, rec):
    ids = by_id(rec)

    def val(m):
        v = m["value"]
        return "not measured" if v is None else f"{v:.1f}" if m["name"] == "temperature" else f"{v:.0f}"

    for i, x in ids.items():
        if i.startswith("M"):
            text = text.replace(f"{{{i}.value}}", val(x)).replace(f"{{{i}.unit}}", x["unit"]) \
                .replace(f"{{{i}.name}}", NAMES.get(x["name"], x["name"]))
        else:
            text = text.replace(f"{{{i}.answer}}", str(x.get("answer", x.get("value"))))
    return text


def render_template(rec, cfg):
    """Deterministic explanation from the chain (same shape as the LLM's; always passes the verifier)."""
    chain = {s["step"]: s for s in rec["chain"]}
    d = rec["decision"]
    reasons = [{"id": d["rule_id"], "text": d["reason"]}]
    for i in chain["interpretation"]["items"]:
        name = NAMES.get(i["name"], i["name"])
        reading = f"{{{i['ref']}.value}} {{{i['ref']}.unit}}"
        if i["status"] in ("out", "borderline"):
            where = direction(i)
            close = " but close to the limit" if i["status"] == "borderline" else ""
            reasons.append({"id": i["ref"], "text": f"Your {name} was {reading}, {where} the usual range{close}."})
        elif i["status"] == "in":
            reasons.append({"id": i["ref"], "text": f"Your {name} was {reading}, within the usual range."})
        elif i["status"] == "not_usable":
            reasons.append({"id": i["ref"], "text": f"Your {name} reading was not clear enough to use."})
    for c in chain["context"]["items"]:
        if c.get("effect") and c.get("could_explain"):
            reasons.append({"id": c["refs"][0], "text": f"You told us something that matters here: {c['effect']}."})
    unc = [u["text"].replace("_", " ") + (": " + ", ".join(WORDS.get(n, n.replace("_", " ")) for n in u["names"])
                                         if u.get("names") else "")
           for u in chain["uncertainty"]["items"] if u["kind"] not in ("rules_draft", "margins_placeholder")]
    return {"summary": d["reason"], "reasons": reasons,
            "uncertainty": ("; ".join(unc).capitalize() + ".") if unc else "",
            "next_step": ""}                     # the fixed advice line is shown by code, right below


def card(expl, rec, cfg, source):
    """The final card: LLM / template text with placeholders filled, plus the fixed parts inserted by code."""
    adv = next(s for s in rec["chain"] if s["step"] == "advice")
    out = {"level": rec["decision"]["level"], "label": LABELS[rec["decision"]["level"]],
           "summary": fill(expl["summary"], rec),
           "reasons": [fill(r["text"], rec) for r in expl["reasons"] if r["text"] != expl["summary"]],
           "uncertainty": fill(expl.get("uncertainty", ""), rec), "next_step": fill(expl.get("next_step", ""), rec),
           "advice": adv["text"], "contacts": adv["contacts"], "contacts_verified": adv["contacts_verified"],
           "disclaimer": adv["disclaimer"], "text_source": source}
    return out


def explain(rec, cfg, use_llm=True, llm=None):
    """-> (card, log) where log = {source, attempts, errors, seconds}. Never raises on LLM problems."""
    log = {"source": "template", "attempts": 0, "errors": [], "seconds": 0.0}
    expl = None
    if use_llm:
        llm = llm or load_llm_config()
        user = json.dumps(facts(rec, cfg), indent=1)
        t0 = time.perf_counter()
        for attempt in range(1 + llm["max_retries"]):
            log["attempts"] += 1
            remaining = llm["timeout_s"] - (time.perf_counter() - t0)
            if remaining <= 0:
                log["errors"].append(["time budget used up"])
                break
            try:
                got, _ = chat_json(SYSTEM, user, SCHEMA, llm, timeout=remaining)
            except LLMError as e:
                log["errors"].append([str(e)])
                break
            errs = verify_explanation(got, rec)
            log["errors"].append(errs)
            if not errs:
                expl, log["source"] = got, "llm" if attempt == 0 else "llm_retry"
                break
            user = (json.dumps(facts(rec, cfg), indent=1) + "\n\nYour previous reply had these problems; fix them:\n- "
                    + "\n- ".join(errs))
        log["seconds"] = round(time.perf_counter() - t0, 2)
    if expl is None:
        expl = render_template(rec, cfg)
        if (bad := verify_explanation(expl, rec)):          # a template that fails is a code bug: say so, keep going
            print(f"WARNING: template failed the verifier for {rec['decision']['rule_id']}: {bad}", flush=True)
            log["errors"].append(["template: " + "; ".join(bad)])
    c = card(expl, rec, cfg, log["source"])
    problems = verify_card(c, rec, cfg)
    if problems:                                          # code bug, never an LLM issue: fail loudly
        raise RuntimeError(f"card check failed: {problems}")
    return c, log


def print_card(c):
    print(f"== {c['label']}  (text: {c['text_source']})")
    print(c["summary"])
    for r in c["reasons"]:
        print(f"  - {r}")
    if c["uncertainty"]:
        print(f"Uncertain: {c['uncertainty']}")
    if c["next_step"]:
        print(f"Next step: {c['next_step']}")
    print(f"ADVICE: {c['advice']}")
    for ct in c["contacts"]:
        print(f"  CALL {ct['name']}: {ct['number']}" + ("" if c["contacts_verified"] else "  (number not yet verified)"))
    print(c["disclaimer"])


if __name__ == "__main__":
    from triage.demo import sample_records
    from triage.rules_engine import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", required=True, help="explain the synthetic demo sessions")
    ap.add_argument("--no-llm", action="store_true", help="template only")
    a = ap.parse_args()
    cfg = load_config()
    for title, rec in sample_records(cfg):
        print(f"\n##### {title}")
        c, log = explain(rec, cfg, use_llm=not a.no_llm)
        print_card(c)
        print(f"[{log['source']}, {log['attempts']} LLM call(s), {log['seconds']} s, errors {log['errors']}]")
