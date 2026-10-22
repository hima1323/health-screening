"""Reasoning layer: the predictor decides, this explains. -> results/explanations/<subject>.jsonl

1. Rule table: per cited feature, does its observed z-score direction match the expected direction under
   high load (learned on training folds, cross-checked with literature)? Split into support / conflict.
2. LLM (Qwen2.5-3B-Instruct via local Ollama, temperature 0, JSON only) writes
   {conclusion, confidence, evidence[], conflicts[], abstain}. It may not change the label.
3. Verifier: label unchanged, confidence = record confidence, every feature name and every number must exist in
   the evidence record. On failure regenerate once with the errors fed back, then abstain.
If Ollama is not reachable, a deterministic template generator is used (recorded as generator=template).
With --fusion the record comes from the agent + fusion model (fusion.py): support / conflict are modality agents
that agree / disagree with the fused label, each cited with its probability and optionally one of its features.

    python src/reasoner.py --subject 0 [--limit 20] [--model qwen2.5:3b-instruct] [--fusion]
"""
import argparse
import json
import re
import urllib.request

from evidence import build, build_fusion
from load_adabase import subject_id
from train import RES

OLLAMA = "http://localhost:11434/api/chat"
MLX = "http://localhost:8080/v1/chat/completions"  # `python -m mlx_lm server` (OpenAI API), optional LoRA adapter
MIN_CONF = 0.6  # below this the explanation must abstain
FEAT_RE = re.compile(r"\b(?:ecg|ppg|eda|rsp|emg|skt|eye|au)_[a-z0-9_]+")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")

SYSTEM = """You explain the output of a cognitive-load classifier. You never change its label.
Use ONLY the features and numbers in the evidence record. Copy numbers exactly as written there.
Do not mention any other feature, number, threshold, count or percentage.
Reply with JSON only:
{"conclusion": "<label from the record>", "confidence": <confidence from the record>,
 "evidence": [{"feature": "<exact feature= string>", "value": <value>, "z": <z>, "statement": "<one short sentence>"}],
 "conflicts": [{"feature": "<exact feature= string>", "value": <value>, "z": <z>, "statement": "<one short sentence>"}],
 "abstain": <the abstain value from the record>}
"evidence" = features listed under SUPPORT, "conflicts" = features listed under CONFLICT."""

SYSTEM_FUSION = """You explain the output of a cognitive-load model built from one agent per sensor modality and a
fusion model that weighs them. You never change the final label.
Use ONLY the agents, features and numbers in the record. Copy numbers exactly as written there.
Do not mention any other agent, feature, number, threshold, count or percentage.
Reply with JSON only:
{"conclusion": "<label from the record>", "confidence": <confidence from the record>,
 "evidence": [{"modality": "<agent>", "probability_high": <its P(high)>, "feature": "<optional: one of its features>",
               "value": <that feature's value>, "z": <that feature's z>, "statement": "<one short sentence>"}],
 "conflicts": [<same shape>],
 "abstain": <the abstain value from the record>}
Exactly one item per agent: every SUPPORT agent once in "evidence", every CONFLICT agent once in "conflicts".
"modality" is the agent= string; "feature" is that agent's feature= string or left out."""


def is_fusion(rec):
    return "agents" in rec


def system(rec):
    return SYSTEM_FUSION if is_fusion(rec) else SYSTEM


def rule_check(rec):
    """Split cited features (or, for fusion, available agents) into those for and against the predicted label."""
    if is_fusion(rec):
        av = sorted([a for a in rec["agents"] if a["available"]], key=lambda a: -abs(a["contribution"]))
        return [a for a in av if a["says"] == rec["label"]], [a for a in av if a["says"] != rec["label"]]
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
    if is_fusion(rec):
        feat = lambda f: f"feature=\"{f['feature']}\" ({f['description']}) value={f['value']} {f['unit']} z={f['z']}"
        line = lambda a: (f"- agent=\"{a['modality']}\": P(high)={a['probability_high']}; says {a['says']}; "
                          f"fusion weight={a['weight']}; contribution={a['contribution']}; quality={a['quality']}; "
                          f"top feature: " + feat(a["top_features"][0]))
        off = [a["modality"] for a in rec["agents"] if not a["available"]]
        return (f"label: {rec['label']}\nconfidence: {rec['confidence']}\nabstain: {str(must_abstain(rec)).lower()}\n"
                f"unavailable or low-quality agents: {off or 'none'}\n"
                f"SUPPORT:\n" + ("\n".join(map(line, support)) or "- none") +
                f"\nCONFLICT:\n" + ("\n".join(map(line, conflict)) or "- none"))
    line = lambda f: (f"- feature=\"{f['feature']}\" means {f['description']}; value={f['value']} {f['unit']}; "
                      f"z={f['z']}; pushes toward {f['pushes_toward']}; "
                      f"matches expected high-load direction: {f['rule_agrees']}")
    must = must_abstain(rec)
    return (f"label: {rec['label']}\nconfidence: {rec['confidence']}\nabstain: {str(must).lower()}\n"
            f"low-quality modalities: {rec['low_quality_modalities'] or 'none'}\n"
            f"SUPPORT:\n" + ("\n".join(map(line, support)) or "- none") +
            f"\nCONFLICT:\n" + ("\n".join(map(line, conflict)) or "- none"))


def must_abstain(rec):
    return rec["confidence"] < MIN_CONF or all(f["feature"].split("_")[0] in rec["low_quality_modalities"]
                                               for f in rec["top_features"])


def schema(rec):
    """JSON schema for Ollama structured output: decoding is constrained to these keys and types. Without it the
    3B model dropped `statement` in 76% of outputs, omitted `abstain` and wrote numbers as strings ("3.22 mm")."""
    item = {"type": "object", "required": ["statement"] + (["modality"] if is_fusion(rec) else ["feature"]),
            "properties": {"modality": {"type": "string"}, "probability_high": {"type": "number"},
                           "feature": {"type": "string"}, "value": {"type": "number"}, "z": {"type": "number"},
                           "statement": {"type": "string"}}}
    return {"type": "object", "required": ["conclusion", "confidence", "evidence", "conflicts", "abstain"],
            "properties": {"conclusion": {"type": "string", "enum": ["high", "low"]}, "confidence": {"type": "number"},
                           "evidence": {"type": "array", "items": item}, "conflicts": {"type": "array", "items": item},
                           "abstain": {"type": "boolean"}}}


def ask_llm(model, messages, fmt="json"):
    """model 'qwen2.5:3b-instruct' -> Ollama (fmt = "json" or a JSON schema); 'mlx:<label>' -> local MLX server
    (label only names the run; no schema support there). Raises OSError if the server is unreachable; malformed
    JSON comes back as {} and fails verification."""
    if model.startswith("mlx:"):
        url, body = MLX, {"messages": messages, "temperature": 0, "max_tokens": 700}
    else:
        url, body = OLLAMA, {"model": model, "messages": messages, "format": fmt, "stream": False,
                             "options": {"temperature": 0, "seed": 0}}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        try:
            resp = json.loads(r.read())
            text = resp["choices"][0]["message"]["content"] if "choices" in resp else resp["message"]["content"]
            return json.loads(text[text.index("{"):text.rindex("}") + 1])  # tolerate ```json fences
        except (ValueError, KeyError, IndexError):
            return {}


def template(rec, support, conflict):
    if is_fusion(rec):
        def item(a):
            f = a["top_features"][0]
            return {"modality": a["modality"], "probability_high": a["probability_high"], "feature": f["feature"],
                    "value": f["value"], "z": f["z"],
                    "statement": f"{a['modality']} agent gives P(high)={a['probability_high']}, led by "
                                 f"{f['description']} at z={f['z']}"}
        return {"conclusion": rec["label"], "confidence": rec["confidence"], "evidence": [item(a) for a in support],
                "conflicts": [item(a) for a in conflict], "abstain": must_abstain(rec)}
    item = lambda f: {"feature": f["feature"], "value": f["value"], "z": f["z"],
                      "statement": f"{f['description']} at z={f['z']} pushes toward {f['pushes_toward']} load"}
    return {"conclusion": rec["label"], "confidence": rec["confidence"], "evidence": [item(f) for f in support],
            "conflicts": [item(f) for f in conflict], "abstain": must_abstain(rec)}


def allowed_numbers(rec):
    nums = {rec["confidence"], rec["probability_high"], *[v for v in rec["quality"].values() if v is not None]}
    for f in rec["top_features"]:
        nums |= {f["value"], f["z"], f["shap"]}
    for a in rec.get("agents", []):
        nums |= {a.get("probability_high"), a["weight"], a["contribution"], a["quality"]}
    return {n for n in nums if n is not None}


def number_ok(tok, allowed):
    try:
        x = float(tok)
    except ValueError:  # e.g. "91.26 F": not a bare number from the record
        return False
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
    if out["abstain"] is not must_abstain(rec):
        errs.append(f"abstain must be {str(must_abstain(rec)).lower()}")
    if out["abstain"] is not True and not out["evidence"] and rule_check(rec)[0]:
        errs.append("evidence must cite the SUPPORT items unless abstaining")
    cited = {f["feature"]: f for f in rec["top_features"]}
    allowed = allowed_numbers(rec)
    agents = {a["modality"]: a for a in rec.get("agents", []) if a["available"]}
    for item in (out["evidence"] or []) + (out["conflicts"] or []):
        if is_fusion(rec) and isinstance(item, dict):
            a = agents.get(item.get("modality"))
            if a is None:
                errs.append(f"unknown or unavailable agent {item.get('modality')}")
                continue
            if item.get("probability_high") is not None and not number_ok(str(item["probability_high"]),
                                                                          {a["probability_high"]}):
                errs.append(f"{a['modality']}.probability_high must be {a['probability_high']}")
            if not str(item.get("statement", "")).strip():
                errs.append(f"{a['modality']} needs a statement")
            if not item.get("feature"):
                continue
            if item["feature"] not in {f["feature"] for f in a["top_features"]}:
                errs.append(f"feature {item['feature']} is not a top feature of the {a['modality']} agent")
                continue
        if not isinstance(item, dict) or item.get("feature") not in cited:
            errs.append(f"unknown feature {item.get('feature') if isinstance(item, dict) else item}")
            continue
        f = cited[item["feature"]]
        if not is_fusion(rec) and not str(item.get("statement", "")).strip():
            errs.append(f"{item['feature']} needs a statement")
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
        msgs = [{"role": "system", "content": system(rec)},
                {"role": "user", "content": prompt(rec, support, conflict)}]
        gen, out = "llm:" + model, ask_llm(model, msgs, schema(rec))
    except OSError:  # Ollama not running / not installed
        gen, out, msgs = "template", template(rec, support, conflict), None
    first_out, first = out, verify(out, rec)
    attempts, errs = 1, first
    if errs and msgs:
        msgs += [{"role": "assistant", "content": json.dumps(out)},
                 {"role": "user", "content": "Rejected by the verifier: " + "; ".join(errs) + ". Fix and resend."}]
        try:
            out, attempts = ask_llm(model, msgs, schema(rec)), 2
            errs = verify(out, rec)
        except OSError:
            pass
    key = "modality" if is_fusion(rec) else "feature"
    cited_first = [i.get(key) for i in (first_out.get("evidence") or []) + (first_out.get("conflicts") or [])
                   if isinstance(i, dict)] if isinstance(first_out, dict) else []
    names = {a["modality"] for a in rec["agents"] if a["available"]} if is_fusion(rec) \
        else {f["feature"] for f in rec["top_features"]}
    if errs:  # abstain, keep the predictor's label untouched
        out = {"conclusion": rec["label"], "confidence": rec["confidence"], "evidence": [], "conflicts": [],
               "abstain": True}
    return {"subject": rec["subject"], "study": rec["study"], "level": rec["level"], "win_start": rec["win_start"],
            "label": rec["label"], "generator": gen, "attempts": attempts, "verified": not errs,
            "errors_first": first, "first_output": first_out, "errors_final": errs, "cited": len(cited_first),
            "cited_in_top6": sum(c in names for c in cited_first),
            "rules": {f.get("feature", f.get("modality")): f.get("rule_agrees") for f in support + conflict},
            "output": out}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--limit", type=int, help="only N windows, evenly spaced over the subject's runs")
    ap.add_argument("--model", default="qwen2.5:3b-instruct")
    ap.add_argument("--fusion", action="store_true", help="explain the agent + fusion model")
    a = ap.parse_args()
    sid = subject_id(a.subject)
    ev, ex = ("evidence_fusion", "explanations_fusion") if a.fusion else ("evidence", "explanations")
    p = RES / ev / f"{sid}.jsonl"
    recs = [json.loads(l) for l in open(p)] if p.exists() else (build_fusion if a.fusion else build)(sid)
    recs = recs[::max(1, len(recs) // a.limit)][:a.limit] if a.limit else recs
    (RES / ex).mkdir(parents=True, exist_ok=True)
    with open(RES / ex / f"{sid}.jsonl", "w") as fh:
        for rec in recs:
            r = explain(rec, a.model)
            fh.write(json.dumps(r) + "\n")
    print(json.dumps(r, indent=1))
    print(f"{sid}: {len(recs)} windows explained with {r['generator']}")
