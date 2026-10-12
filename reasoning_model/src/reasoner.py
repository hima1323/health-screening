"""Reasoning layer: the predictor decides, this explains. -> results/explanations/<subject>.jsonl

1. Rule table: per cited feature, does its observed z-score direction match the expected direction under
   high load (learned on training folds, cross-checked with literature)? Split into support / conflict.
2. LLM (Qwen2.5-3B-Instruct via local Ollama, temperature 0, JSON only) writes
   {conclusion, confidence, evidence[], conflicts[], abstain}. It may not change the label.
3. Verifier: label unchanged, confidence = record confidence, every feature name and every number must exist in
   the evidence record. On failure regenerate once with the errors fed back, then abstain.
If Ollama is not reachable, a deterministic template generator is used (recorded as generator=template).

    python src/reasoner.py --subject 0 [--limit 20] [--model qwen2.5:3b-instruct]
"""
import argparse
import json
import re
import urllib.request

from evidence import build
from load_adabase import subject_id
from train import RES

OLLAMA = "http://localhost:11434/api/chat"
MIN_CONF = 0.6  # below this the explanation must abstain
FEAT_RE = re.compile(r"\b(?:ecg|ppg|eda|rsp|emg|skt|eye|au)_[a-z0-9_]+")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")

SYSTEM = """You explain the output of a cognitive-load classifier. You never change its label.
Use ONLY the features and numbers in the evidence record. Copy numbers exactly as written there.
Do not mention any other feature, number, threshold, count or percentage.
Reply with JSON only:
{"conclusion": "<label from the record>", "confidence": <confidence from the record>,
 "evidence": [{"feature": "<name>", "value": <value>, "z": <z>, "statement": "<one short sentence>"}],
 "conflicts": [{"feature": "<name>", "value": <value>, "z": <z>, "statement": "<one short sentence>"}],
 "abstain": <true if confidence < 0.6 or all cited signals are low quality, else false>}
"evidence" = features listed under SUPPORT, "conflicts" = features listed under CONFLICT."""


def rule_check(rec):
    """Split cited features into those consistent with the predicted label and those against it."""
    support, conflict = [], []
    for f in rec["top_features"]:
        expected = f["learned_direction_high_load"]
        if expected == "none":
            expected = {"mixed": "none"}.get(f["literature_direction_high_load"], f["literature_direction_high_load"])
        observed = "+" if (f["z"] or 0) > 0 else "-"
        # under a 'high' label a feature supports it if it moved in the high-load direction, and vice versa
        agrees = (observed == expected) == (rec["label"] == "high") if expected != "none" else None
        f = {**f, "rule_agrees": agrees}
        (support if f["pushes_toward"] == rec["label"] else conflict).append(f)
    return support, conflict


def prompt(rec, support, conflict):
    line = lambda f: (f"- {f['feature']} ({f['description']}): value={f['value']} {f['unit']}, z={f['z']}, "
                      f"pushes toward {f['pushes_toward']}, matches expected high-load direction: {f['rule_agrees']}")
    return (f"label: {rec['label']}\nconfidence: {rec['confidence']}\n"
            f"low-quality modalities: {rec['low_quality_modalities'] or 'none'}\n"
            f"SUPPORT:\n" + ("\n".join(map(line, support)) or "- none") +
            f"\nCONFLICT:\n" + ("\n".join(map(line, conflict)) or "- none"))


def ask_llm(model, messages):
    """Raises OSError if Ollama is unreachable; malformed JSON comes back as {} and fails verification."""
    body = json.dumps({"model": model, "messages": messages, "format": "json", "stream": False,
                       "options": {"temperature": 0, "seed": 0}}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        try:
            return json.loads(json.loads(r.read())["message"]["content"])
        except (ValueError, KeyError):
            return {}


def template(rec, support, conflict):
    item = lambda f: {"feature": f["feature"], "value": f["value"], "z": f["z"],
                      "statement": f"{f['description']} at z={f['z']} pushes toward {f['pushes_toward']} load"}
    return {"conclusion": rec["label"], "confidence": rec["confidence"], "evidence": [item(f) for f in support],
            "conflicts": [item(f) for f in conflict], "abstain": rec["confidence"] < MIN_CONF}


def allowed_numbers(rec):
    nums = {rec["confidence"], rec["probability_high"], *[v for v in rec["quality"].values() if v is not None]}
    for f in rec["top_features"]:
        nums |= {f["value"], f["z"], f["shap"]}
    return {n for n in nums if n is not None}


def number_ok(tok, allowed):
    x = float(tok)
    tol = 0.5 * 10 ** -(len(tok.split(".")[1]) if "." in tok and "e" not in tok else 0)
    return any(abs(x - a) <= tol + 1e-9 or abs(x - a) <= 1e-3 * abs(a) for a in allowed)


def verify(out, rec):
    """Return list of errors; empty = verified."""
    errs = []
    if not isinstance(out, dict) or not {"conclusion", "confidence", "evidence", "conflicts", "abstain"} <= out.keys():
        return ["missing keys"]
    if out["conclusion"] != rec["label"]:
        errs.append(f"conclusion must be '{rec['label']}'")
    if not isinstance(out["confidence"], (int, float)) or abs(out["confidence"] - rec["confidence"]) > 1e-3:
        errs.append(f"confidence must be {rec['confidence']}")
    if rec["confidence"] < MIN_CONF and out["abstain"] is not True:
        errs.append("abstain must be true (confidence below 0.6)")
    cited = {f["feature"]: f for f in rec["top_features"]}
    allowed = allowed_numbers(rec)
    for item in (out["evidence"] or []) + (out["conflicts"] or []):
        if not isinstance(item, dict) or item.get("feature") not in cited:
            errs.append(f"unknown feature {item.get('feature') if isinstance(item, dict) else item}")
            continue
        f = cited[item["feature"]]
        for k in ("value", "z"):
            if item.get(k) is not None and not number_ok(str(item[k]), {f[k]}):
                errs.append(f"{item['feature']}.{k} must be {f[k]}")
    text = json.dumps([out.get("conclusion"), [i.get("statement", "") if isinstance(i, dict) else i
                                               for i in (out["evidence"] or []) + (out["conflicts"] or [])]])
    for name in set(FEAT_RE.findall(text)) - set(cited):
        errs.append(f"feature {name} is not in the evidence record")
    names_stripped = re.sub(r"(?i)pNN50|\bAU\s?\d+|\bunit \d+", "", FEAT_RE.sub("", text))  # digits inside names
    for tok in NUM_RE.findall(names_stripped):
        if not number_ok(tok, allowed):
            errs.append(f"number {tok} is not in the evidence record")
    return errs


def explain(rec, model):
    support, conflict = rule_check(rec)
    try:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(rec, support, conflict)}]
        gen, out = "llm:" + model, ask_llm(model, msgs)
    except OSError:  # Ollama not running / not installed
        gen, out, msgs = "template", template(rec, support, conflict), None
    first = verify(out, rec)
    attempts, errs = 1, first
    if errs and msgs:
        msgs += [{"role": "assistant", "content": json.dumps(out)},
                 {"role": "user", "content": "Rejected by the verifier: " + "; ".join(errs) + ". Fix and resend."}]
        try:
            out, attempts = ask_llm(model, msgs), 2
            errs = verify(out, rec)
        except OSError:
            pass
    cited_first = [i.get("feature") for i in (out.get("evidence") or []) + (out.get("conflicts") or [])
                   if isinstance(i, dict)] if isinstance(out, dict) else []
    names = {f["feature"] for f in rec["top_features"]}
    if errs:  # abstain, keep the predictor's label untouched
        out = {"conclusion": rec["label"], "confidence": rec["confidence"], "evidence": [], "conflicts": [],
               "abstain": True}
    return {"subject": rec["subject"], "study": rec["study"], "level": rec["level"], "win_start": rec["win_start"],
            "label": rec["label"], "generator": gen, "attempts": attempts, "verified": not errs,
            "errors_first": first, "errors_final": errs, "cited": len(cited_first),
            "cited_in_top6": sum(c in names for c in cited_first), "rules": {f["feature"]: f["rule_agrees"]
                                                                            for f in support + conflict},
            "output": out}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--limit", type=int, help="only the first N windows")
    ap.add_argument("--model", default="qwen2.5:3b-instruct")
    a = ap.parse_args()
    sid = subject_id(a.subject)
    p = RES / "evidence" / f"{sid}.jsonl"
    recs = [json.loads(l) for l in open(p)] if p.exists() else build(sid)
    recs = recs[:a.limit] if a.limit else recs
    (RES / "explanations").mkdir(parents=True, exist_ok=True)
    with open(RES / "explanations" / f"{sid}.jsonl", "w") as fh:
        for rec in recs:
            r = explain(rec, a.model)
            fh.write(json.dumps(r) + "\n")
    print(json.dumps(r, indent=1))
    print(f"{sid}: {len(recs)} windows explained with {r['generator']}")
