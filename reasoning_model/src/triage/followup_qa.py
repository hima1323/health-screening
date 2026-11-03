"""Follow-up Q&A after the result card (starter kit phase E4).

Answers come ONLY from the session record and the knowledge text, retrieved by section key:
knowledge/triage_knowledge.md once a clinician approved it, or knowledge/triage_knowledge_DRAFT.md in demo mode.
  1. route the question to section keys by keywords (code); medicines, doses, diagnoses -> the fixed refusal
     (section out_of_scope_questions); a question about nothing the check covers -> section off_topic;
  2. crisis, the URGENT result and refusals are answered with the fixed section text, never by the LLM;
  3. otherwise one local LLM call writes a short answer from those sections + the record facts (placeholders only for
     numbers), verified (verify.verify_answer); one retry, else the retrieved section text itself.

    python -m triage.followup_qa --demo "why was my heart rate measured twice?"     (from reasoning_model/src)
"""
import argparse
import json
import re
import time

from triage.evidence import ROOT
from triage.llm import LLMError, chat_json, load_llm_config
from triage.verify import verify_answer

KNOWLEDGE = ROOT / "knowledge"
REFUSAL = "out_of_scope_questions"
OFF_TOPIC = "off_topic"
FIXED = {"crisis", REFUSAL, OFF_TOPIC, "result_urgent", "contacts", "data_privacy"}          # answered verbatim, never rephrased by the LLM

# keyword -> section; checked in order, a question can match several sections
ROUTES = [
    (r"hurt(ing)? (my)?self|harm(ing)? (my)?self|self.?harm|suicid|kill(ing)? myself|end(ing)? my life|"
     r"better off dead|don'?t want to live", ["crisis"]),
    (r"\b(call|phone|number|helpline|ambulance)\b", ["contacts"]),
    (r"\b(data|privacy|stored|store|recorded|recording|video kept)\b", ["data_privacy"]),
    (r"medicine|medication|drug|tablet|pill|dose|dosage|\bmg\b|prescri|antibiotic|paracetamol|ibuprofen|aspirin|"
     r"diagnos|disease|illness|condition do i|what do i have|do i have|is it (a|an) |cancer|covid|infection do",
     [REFUSAL]),
    (r"repeat|again|twice|two readings|second (reading|measurement)|re-?measure", ["why_repeated"]),
    (r"heart|pulse|\bbpm\b|beat|coffee|caffeine|\btea\b|smok|exercis|stairs|\bran\b|running", ["heart_rate"]),
    (r"breath|respirat", ["breathing_fast"]),
    (r"temperature|fever|feverish|\bhot\b|chills|thermal", ["temperature_high"]),
    (r"mood|sad|down|depress|anxious|anxiety|worr|stress|nervous|counsel", ["mood_screen_positive"]),
    (r"blood pressure|oxygen|spo2|accura|reliab|how does|how do you measure|camera|limit|trust", ["measurement_limits"]),
    (r"what (should|do) i do|what now|next|mean|result|serious|doctor|hospital|emergency|why|worse|matter",
     ["result"]),
]
LEVEL_SECTION = {"URGENT": "result_urgent", "SEE_DOCTOR_SOON": "result_see_doctor_soon",
                 "SELF_CARE": "result_self_care", "NOT_SUITABLE": "result_not_suitable", "RETAKE": "measurement_limits",
                 "REMEASURE": "why_repeated"}
SCHEMA = {"type": "object", "required": ["answer", "sources"],
          "properties": {"answer": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}}}
SYSTEM = """You answer a follow-up question from a person who just used a health kiosk.
Use ONLY the knowledge sections and the session facts you are given. If they do not answer the question, say you
cannot answer that here and suggest asking a doctor.
Reply with JSON: answer (two to four short sentences, plain English, speak to the person as "you") and sources (the
section keys you used). Write NO numbers: to mention a reading use its placeholder exactly, e.g. "{M1.value} {M1.unit}".
Do not name illnesses or conditions, do not mention medicines or doses, and never say a doctor is not needed."""


def parse_knowledge(text):
    meta = {}
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if m:
        meta = {k.strip(): v.strip() for k, v in (ln.split(":", 1) for ln in m.group(1).splitlines() if ":" in ln)}
    parts = re.split(r"^## +(\S+)\s*$", text, flags=re.M)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}
    return {"status": meta.get("status", "unknown"), "reviewed_by": meta.get("reviewed_by"), "sections": sections}


def load_knowledge(demo=False):
    """The approved text; the DRAFT only in demo mode (safety rule 2)."""
    approved = parse_knowledge((KNOWLEDGE / "triage_knowledge.md").read_text(encoding="utf-8"))
    if approved["status"] == "approved":
        return approved
    if not demo:
        raise RuntimeError("no clinician-approved knowledge text yet: the follow-up Q&A runs only in demo mode")
    return parse_knowledge((KNOWLEDGE / "triage_knowledge_DRAFT.md").read_text(encoding="utf-8"))


def contacts_text(cfg, kind):
    return " or ".join(f"{c['name']} ({c['number']})" for c in cfg["contacts"][kind])


def fixed_text(key, knowledge, cfg):
    return knowledge["sections"][key].replace("{crisis}", contacts_text(cfg, "crisis")) \
        .replace("{emergency}", contacts_text(cfg, "emergency")).strip('"')


def route(question, rec):
    """-> section keys, most specific first; [OFF_TOPIC] when nothing matches."""
    q = question.lower()
    keys = []
    for pattern, targets in ROUTES:
        if re.search(pattern, q):
            keys += targets
    if "crisis" in keys:
        return ["crisis"]
    if REFUSAL in keys:
        return [REFUSAL]
    out = []
    for k in keys:
        if k == "heart_rate":
            out += _heart_sections(rec)
        elif k == "result":
            out.append(LEVEL_SECTION[rec["decision"]["level"]])
        else:
            out.append(k)
    return list(dict.fromkeys(out)) or [OFF_TOPIC]


def _heart_sections(rec):
    hr = [i for s in rec["chain"] if s["step"] == "interpretation" for i in s["items"]
          if i["name"] == "heart_rate" and "normal" in i]
    if hr and hr[0]["value"] < (hr[0]["normal"][0] or 0):
        return ["heart_rate_low"]
    return ["heart_rate_high"] if hr and hr[0]["status"] != "in" else ["heart_rate_high", "heart_rate_low"]


def session_facts(rec):
    d = rec["decision"]
    return {"result_level": d["level"].replace("_", " ").lower(), "why": d["reason"],
            "readings": [{"ref": m["id"], "measure": m["name"].replace("_", " "), "value": f"{{{m['id']}.value}}",
                          "unit": f"{{{m['id']}.unit}}", "measured_twice": len(m.get("repeat_values") or []) >= 2}
                         for m in rec["measurements"] if m["value"] is not None]}


def answer(question, rec, cfg, knowledge, use_llm=True, llm=None):
    """-> {answer, sources, by: fixed | llm | llm_retry | section_text, errors, seconds}"""
    from triage.explainer import fill
    keys = [k for k in route(question, rec) if k in knowledge["sections"]] or [REFUSAL]
    if keys[0] in FIXED:
        return {"answer": fixed_text(keys[0], knowledge, cfg), "sources": keys[:1], "by": "fixed", "errors": [],
                "seconds": 0.0}
    fallback = {"answer": " ".join(fixed_text(k, knowledge, cfg) for k in keys), "sources": keys,
                "by": "section_text", "errors": [], "seconds": 0.0}
    if not use_llm:
        return fallback
    llm = llm or load_llm_config()
    user = json.dumps({"question": question, "knowledge_sections": {k: knowledge["sections"][k] for k in keys},
                       "session_facts": session_facts(rec)}, indent=1)
    t0 = time.perf_counter()
    for attempt in range(1 + llm["max_retries"]):
        remaining = llm["timeout_s"] - (time.perf_counter() - t0)
        if remaining <= 0:
            fallback["errors"].append(["time budget used up"])
            break
        try:
            got, _ = chat_json(SYSTEM, user, SCHEMA, llm, timeout=remaining)
        except LLMError as e:
            fallback["errors"].append([str(e)])
            break
        errs = verify_answer(got.get("answer", ""), rec, keys, got.get("sources") or [])
        fallback["errors"].append(errs)
        if not errs:
            return {"answer": fill(got["answer"], rec), "sources": got["sources"],
                    "by": "llm" if attempt == 0 else "llm_retry", "errors": fallback["errors"],
                    "seconds": round(time.perf_counter() - t0, 2)}
        user += "\n\nYour previous reply had these problems; fix them:\n- " + "\n- ".join(errs)
    fallback["seconds"] = round(time.perf_counter() - t0, 2)
    return fallback


if __name__ == "__main__":
    from triage.demo import sample_records
    from triage.rules_engine import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--demo", action="store_true", required=True, help="use the DRAFT knowledge text")
    ap.add_argument("--sample", type=int, default=1, help="which demo session (0-based)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    title, rec = sample_records(cfg)[a.sample]
    res = answer(" ".join(a.question), rec, cfg, load_knowledge(demo=True), use_llm=not a.no_llm)
    print(f"[session: {title}; level {rec['decision']['level']}]")
    print(json.dumps(res, indent=1))
