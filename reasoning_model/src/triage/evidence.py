"""Evidence record for one triage session (schema: configs/triage/evidence.schema.json).

Everything the rule engine, the reasoning chain and the explainer may use is in this record, under a stable ID:
measurements M1.., answers Q1.., scores S1... The rule engine fills `decision`, reasoning_chain.py fills `chain`.
`wellness` (optional cognitive-load panel, P7) is written here but never read by rules_engine.py.

    python -m triage.evidence --check <record.json>      (from reasoning_model/src)
"""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # reasoning_model/
CONFIG = ROOT / "configs" / "triage"
SCHEMA = CONFIG / "evidence.schema.json"


def code_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=5).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def new_record(session_id, cfg, code=None):
    return {"session_id": session_id,
            "version": {"rules": cfg["rules"]["version"], "ranges": cfg["ranges"]["version"],
                        "code": code or code_version()},
            "measurements": [], "answers": [], "scores": [], "flags": [], "decision": None, "chain": None}


def _next_id(items, prefix):
    return f"{prefix}{len(items) + 1}"


def add_measurement(rec, name, value, unit, quality, source, error_margin=None, repeat_values=None):
    """value = the reading (mean of `repeat_values` when there are repeats); None = could not be measured."""
    m = {"id": _next_id(rec["measurements"], "M"), "name": name, "value": value, "unit": unit,
         "error_margin": error_margin, "quality": quality, "source": source,
         "n_readings": len(repeat_values) if repeat_values else int(value is not None)}
    if repeat_values:
        m["repeat_values"] = list(repeat_values)
    rec["measurements"].append(m)
    return m["id"]


def add_answer(rec, item, answer, confirmed=True):
    if isinstance(answer, bool):  # a YAML/JSON true/false where "yes"/"no" was meant
        raise TypeError(f"answer to {item} must be a string or a number, not {answer!r}")
    a = {"id": _next_id(rec["answers"], "Q"), "item": item, "answer": answer, "confirmed": confirmed}
    rec["answers"].append(a)
    return a["id"]


def add_score(rec, name, value):
    s = {"id": _next_id(rec["scores"], "S"), "name": name, "value": value}
    rec["scores"].append(s)
    return s["id"]


def validate(rec):
    """Return a list of schema errors; empty = valid."""
    import jsonschema
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(rec)]
    for key in ("measurements", "answers", "scores"):
        ids = [x["id"] for x in rec.get(key, []) if isinstance(x, dict) and "id" in x]
        errs += [f"{key}: duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return errs


def by_id(rec):
    return {x["id"]: x for key in ("measurements", "answers", "scores") for x in rec[key]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True, help="evidence record JSON file")
    errs = validate(json.loads(Path(ap.parse_args().check).read_text(encoding="utf-8")))
    print("\n".join(errs) or "valid")
