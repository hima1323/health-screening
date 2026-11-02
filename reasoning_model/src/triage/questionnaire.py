"""Kiosk questionnaire from configs/triage/questionnaire.yaml + red_flags.yaml (starter kit phase E3).

Order: consent -> scope (age, pregnancy) -> red flags -> context -> duration -> PHQ-2 / GAD-2 (+ self-harm last).
Answers are "yes"/"no"/option strings or numbers. A free-text answer may be mapped to an option, first by the item's
synonyms and then by the local LLM, but the mapped option is only a proposal: it is stored with `confirmed: false`
unless the user confirms it (otherwise the kiosk falls back to the answer buttons). Scores (PHQ2, GAD2) are computed
here by code, only when every item of the score was answered.
"""
import re

from triage.evidence import add_answer, add_score

YES_WORDS = {"yes", "y", "yeah", "yep", "i do", "i have", "true"}
NO_WORDS = {"no", "n", "nope", "not", "never", "i don't", "i do not", "i haven't", "false", "none"}


def questions(cfg):
    """Ordered list of {item, section, question, options | type, ask_if}."""
    q, flags = cfg["questionnaire"], cfg["red_flags"]["items"]
    out = []
    for section in q["order"]:
        sec = q["sections"][section]
        items = sec["items"]
        if isinstance(items, list):                       # red-flag section: wording lives in red_flags.yaml
            items = {i: {"question": flags[i]["question"], "options": sec["options"]} for i in items}
        for item, spec in items.items():
            spec = dict(spec or {})
            if not spec.get("question") and item in flags:
                spec["question"] = flags[item]["question"]
            out.append({"item": item, "section": section, "question": spec["question"],
                        "options": _option_values(spec.get("options")), "type": spec.get("type"),
                        "ask_if": spec.get("ask_if"), "intro": sec.get("intro")})
    return out


def _option_values(options):
    if not options:
        return None
    return [o["text"] if isinstance(o, dict) else o for o in options]


def option_value(cfg, item, text):
    """PHQ/GAD option text -> 0..3; yes/no -> unchanged."""
    for sec in cfg["questionnaire"]["sections"].values():
        spec = sec["items"].get(item) if isinstance(sec["items"], dict) else None
        if spec and spec.get("options") and isinstance(spec["options"][0], dict):
            return {o["text"]: o["value"] for o in spec["options"]}[text]
    return text


def should_ask(q, answers):
    cond = q.get("ask_if")
    return not cond or answers.get(cond["answer"]) == cond["equals"]


def pending(cfg, answers, sections=None):
    """Questions still to ask, in order (skips answered ones and those whose ask_if does not hold)."""
    return [q for q in questions(cfg) if q["item"] not in answers and should_ask(q, answers)
            and (sections is None or q["section"] in sections)]


def scores(cfg, answers):
    """{"PHQ2": 0-6, ...} for every score whose items were all answered."""
    out = {}
    for name, spec in cfg["questionnaire"]["scores"].items():
        vals = [answers.get(i) for i in spec["items"]]
        if all(isinstance(v, (int, float)) for v in vals):
            out[name] = sum(vals)
    return out


def record_answers(rec, cfg, answers, unconfirmed=()):
    """answers: {item: value} with PHQ/GAD answers as option text or 0-3; items in `unconfirmed` are stored with
    confirmed=false. Adds the scores. Returns the numeric answers dict."""
    numeric = {}
    for item, v in answers.items():
        if isinstance(v, str) and not v.isdigit():
            try:
                v = option_value(cfg, item, v)
            except KeyError:
                pass
        numeric[item] = v
        add_answer(rec, item, v, confirmed=item not in unconfirmed)
    for name, v in scores(cfg, {k: v for k, v in numeric.items() if k not in unconfirmed}).items():
        add_score(rec, name, v)
    return numeric


# ---------------------------------------------------------------- free text -> proposed option (to be confirmed)

def map_free_text(cfg, q, text, use_llm=False, llm=None):
    """-> {"option": proposal or None, "by": "synonym" | "words" | "llm" | None}. The caller asks the user to confirm
    the proposal and stores it confirmed only then; None -> show the buttons."""
    t = " ".join(re.findall(r"[a-z']+|\d+", text.lower()))
    if q.get("type") == "number":
        m = re.search(r"\d+", t)
        return {"option": int(m.group()) if m else None, "by": "words" if m else None}
    opts = q.get("options") or []
    for o in sorted(opts, key=len, reverse=True):               # the option itself, e.g. "several days"
        if re.search(rf"\b{re.escape(o.lower())}\b", t):
            return {"option": o, "by": "words"}
    syn = cfg["red_flags"]["items"].get(q["item"], {}).get("synonyms", [])
    if "yes" in opts and any(s.lower() in t for s in syn) and not _negated(t):
        return {"option": "yes", "by": "synonym"}
    if "yes" in opts and re.search(r"\b(don'?t know|not sure|unsure|maybe|no idea|can'?t say)\b", t):
        return {"option": None, "by": None}                    # unclear: show the buttons
    if "yes" in opts:
        words = set(t.split()) | {t}
        if words & NO_WORDS or _negated(t):
            return {"option": "no", "by": "words"}
        if words & YES_WORDS:
            return {"option": "yes", "by": "words"}
    if use_llm and opts:
        from triage.llm import LLMError, chat_json
        schema = {"type": "object", "required": ["option"],
                  "properties": {"option": {"type": "string", "enum": opts + ["unclear"]}}}
        system = ("Map the person's reply to exactly one of the allowed options, or 'unclear' if it does not clearly "
                  "fit one. Reply with JSON only.")
        try:
            got = chat_json(system, f"Question: {q['question']}\nAllowed options: {opts}\nReply: {text}",
                            schema, llm)[0]["option"]
            return {"option": got if got in opts else None, "by": "llm" if got in opts else None}
        except LLMError:
            pass
    return {"option": None, "by": None}


def _negated(t):
    return bool(re.search(r"\b(no|not|never|don't|dont|haven't|havent|didn't|didnt|without)\b", t))
