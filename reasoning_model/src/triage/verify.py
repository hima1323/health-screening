"""Verifier for every LLM text (explanation and follow-up answers), starter kit phase E4.

Checks, each returning a plain error string the LLM gets back on its one retry:
  - placeholders: only {M1.value} / {M1.unit} / {M1.name} style references to IDs that exist in the record;
  - no literal digits outside placeholders (every number shown comes from the record via a placeholder);
  - every fired-rule reason is mentioned (the reason list contains the deciding rule id);
  - the level wording is consistent (no other level's wording, no "you don't need a doctor");
  - a reading called high / low really is above / below its usual range (reading_claims);
  - no forbidden terms: disorder names, medicine names, dosing;
  - the crisis contacts are present when the self-harm rule fired (checked on the final card, which code assembles).
"""
import re

from triage.evidence import by_id

PLACEHOLDER = re.compile(r"\{([MQS][0-9]+)\.(value|unit|name|answer)\}")
ANY_BRACES = re.compile(r"\{[^{}]*\}")

# Disorder / diagnosis names, medicines and dosing words: never in generated text (safety rule 5). Matched as whole
# words, case-insensitive. The knowledge text and the fixed messages are written to avoid them.
DIAGNOSES = ["tachycardia", "bradycardia", "arrhythmia", "atrial fibrillation", "afib", "hypertension",
             "hypotension", "hypothermia", "hyperthermia", "sepsis", "septic", "pneumonia", "covid", "influenza",
             "flu", "asthma", "copd", "heart attack", "myocardial", "infarction", "angina", "stroke", "diabetes",
             "depression", "depressive disorder", "anxiety disorder", "panic disorder", "bipolar", "ptsd",
             "dementia", "cancer", "anaemia", "anemia", "hyperthyroid", "hypothyroid", "fever of unknown origin",
             "you are suffering from", "you suffer from"]
MEDICINES = ["aspirin", "paracetamol", "acetaminophen", "ibuprofen", "naproxen", "antibiotic", "antibiotics",
             "antidepressant", "antidepressants", "beta blocker", "beta-blocker", "inhaler", "insulin", "statin",
             "nitroglycerin", "epipen", "adrenaline", "epinephrine", "benzodiazepine", "sertraline", "fluoxetine"]
DOSING = ["mg", "milligram", "milligrams", "dose", "dosage", "tablet", "tablets", "pill", "pills", "twice a day",
          "once a day", "every 4 hours", "every 6 hours"]
REASSURANCE = ["you don't need a doctor", "you do not need a doctor", "no need to see a doctor", "no need for a doctor",
               "you don't need to see", "you do not need to see", "nothing to worry about", "you are healthy",
               "you are fine", "you're fine", "perfectly healthy"]
LEVEL_WORDS = {"URGENT": ["urgent", "emergency", "right away", "immediately", "get help now"],
               "SEE_DOCTOR_SOON": ["see a doctor soon", "in the next few days"],
               "SELF_CARE": ["self-care", "self care", "no warning signs"],
               "RETAKE": ["retake", "try again", "measure again"],
               "REMEASURE": ["rest", "measure again", "repeated"],
               "NOT_SUITABLE": ["not designed", "not suitable"]}


def _words(terms, text):
    low = text.lower()
    return [t for t in terms if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low)]


def forbidden_terms(text):
    return _words(DIAGNOSES + MEDICINES + DOSING + REASSURANCE, text)


def check_placeholders(text, rec):
    ids = by_id(rec)
    errs = []
    for m in ANY_BRACES.finditer(text):
        p = PLACEHOLDER.fullmatch(m.group())
        if not p:
            errs.append(f"invalid placeholder {m.group()}: use only {{M1.value}}, {{M1.unit}} style references")
        elif p.group(1) not in ids:
            errs.append(f"placeholder {m.group()} refers to {p.group(1)}, which is not in the record")
        elif p.group(2) in ("value", "unit", "name") and not p.group(1).startswith("M"):
            errs.append(f"placeholder {m.group()}: .{p.group(2)} exists only for measurements (M*)")
    return errs


def check_digits(text, fixed=()):
    """`fixed` = approved config texts (rule reasons) that may be quoted verbatim, digits included."""
    bare = ANY_BRACES.sub("", text)
    for f in fixed:
        bare = bare.replace(f, "")
    return ["write no numbers: use a placeholder such as {M1.value} for every number"] if re.search(r"\d", bare) \
        else []


def level_conflicts(text, level):
    """Wording of a different (more or less severe) level than the one decided."""
    others = {"URGENT"} if level != "URGENT" else {"SELF_CARE"}
    if level == "SELF_CARE":
        others |= {"SEE_DOCTOR_SOON"}
    return [f"the text sounds like level {o} ({', '.join(hits)}), but the level is {level}"
            for o in sorted(others) if (hits := _words(LEVEL_WORDS[o], text))]


MEASURE_WORDS = {"heart_rate": r"heart ?rate|pulse", "resp_rate": r"breathing|respirat", "temperature": r"temperature",
                 "spo2": r"oxygen", "sbp": r"blood pressure", "dbp": r"blood pressure"}
SAY = {"resp_rate": "breathing rate", "spo2": "oxygen level", "sbp": "blood pressure", "dbp": "blood pressure"}
HIGH_WORDS = r"\b(high|higher|fast|faster|raised|elevated|above|too high|increased)\b"
LOW_WORDS = r"\b(low|lower|slow|slower|below|too low|decreased|reduced)\b"


def reading_claims(text, rec):
    """A sentence that calls a reading high / low must match how the chain read it (within / above / below the
    usual range). Catches e.g. 'you have a high heart rate' when it was 86 bpm and inside the range."""
    chain = {s["step"]: s for s in rec.get("chain") or []}
    interp = chain.get("interpretation", {}).get("items", [])
    text = text.lower()
    # texts written by code (context effects, uncertainty notes, the rule reason) may be quoted as they are
    fixed = [c.get("effect") for c in chain.get("context", {}).get("items", [])] + \
            [u.get("text") for u in chain.get("uncertainty", {}).get("items", [])] + \
            [(rec.get("decision") or {}).get("reason")]
    for f in fixed:
        if f:
            text = text.replace(f.lower(), "")
    errs = []
    for sentence in re.split(r"[.!?;,:\n]|\b(?:and|but|while|whereas|although)\b", text):   # clause by clause
        for i in interp:
            pat = MEASURE_WORDS.get(i["name"])
            if not pat or not re.search(pat, sentence) or i.get("status") not in ("in", "borderline", "out"):
                continue
            # "blood pressure" covers both numbers: high / low is right if either number is
            same = [j for j in interp if MEASURE_WORDS.get(j["name"]) == pat
                    and j.get("status") in ("in", "borderline", "out")]
            above = any(j["normal"][1] is not None and j["value"] > j["normal"][1] for j in same)
            below = any(j["normal"][0] is not None and j["value"] < j["normal"][0] for j in same)
            if i is not same[0]:                                  # report once per measure phrase
                continue
            says_high, says_low = re.search(HIGH_WORDS, sentence), re.search(LOW_WORDS, sentence)
            if says_high and not says_low and not above:
                errs.append(f"the text calls the {SAY.get(i['name'], i['name'].replace('_', ' '))} high, but it was "
                            f"{'below' if below else 'within'} the usual range")
            if says_low and not says_high and not below:
                errs.append(f"the text calls the {SAY.get(i['name'], i['name'].replace('_', ' '))} low, but it was "
                            f"{'above' if above else 'within'} the usual range")
    return sorted(set(errs))


def verify_explanation(expl, rec):
    """expl = {summary, reasons[{id, text}], uncertainty, next_step} from the LLM. -> list of errors."""
    d = rec["decision"]
    if not isinstance(expl, dict) or not isinstance(expl.get("reasons"), list):
        return ["reply must be JSON with summary, reasons (list of {id, text}), uncertainty and next_step"]
    texts = [expl.get("summary", ""), expl.get("uncertainty", ""), expl.get("next_step", "")] + \
            [r.get("text", "") for r in expl["reasons"] if isinstance(r, dict)]
    full = "\n".join(t for t in texts if isinstance(t, str))
    errs = check_placeholders(full, rec) + check_digits(full, [d["reason"]])
    if d["rule_id"] not in [r.get("id") for r in expl["reasons"] if isinstance(r, dict)]:
        errs.append(f"the reasons must include the rule that decided, id {d['rule_id']}")
    errs += level_conflicts(full, d["level"]) + reading_claims(full, rec)
    if (bad := forbidden_terms(full)):
        errs.append(f"remove these words (no diagnoses, medicines, doses or reassurance): {', '.join(bad)}")
    return errs


def verify_card(card, rec, cfg):
    """The final card assembled by code: crisis contacts when R02 fired, emergency number when URGENT."""
    errs = []
    d = rec["decision"]
    numbers = {c["number"] for c in card.get("contacts", [])}
    if "show_crisis_contacts" in d["actions"] and not {c["number"] for c in cfg["contacts"]["crisis"]} <= numbers:
        errs.append("crisis contacts missing")
    if d["level"] == "URGENT" and not {c["number"] for c in cfg["contacts"]["emergency"]} <= numbers:
        errs.append("emergency number missing")
    if card.get("disclaimer") != cfg["rules"]["disclaimer"]:
        errs.append("disclaimer missing")
    if card.get("level") != d["level"]:
        errs.append("card level differs from the rule engine's level")
    return errs


def verify_answer(text, rec, allowed_sources, sources):
    """Follow-up answer: placeholders, digits, forbidden words, and only the retrieved sources cited."""
    errs = check_placeholders(text, rec) + check_digits(text) + reading_claims(text, rec)
    if (bad := forbidden_terms(text)):
        errs.append(f"remove these words: {', '.join(bad)}")
    if not sources or not set(sources) <= set(allowed_sources):
        errs.append(f"cite only these sources: {', '.join(allowed_sources)}")
    return errs
