"""JSON schemas for every triage config, the vignettes and the evidence table (starter kit phase E0.2).

load_config() runs validate_config() before the semantic checks in rules_engine.check_config(): types, required
provenance fields (version, status, reviewed_by, review_date on every file; a review block on every rule) and the
allowed status values. The evidence record has its own schema (configs/triage/evidence.schema.json, evidence.py).
jsonschema is used instead of pydantic (already installed; same checks).

    python -m triage.schema                    validate all configs, evidence/evidence_table.csv and vignettes
"""
import csv
from pathlib import Path

import jsonschema
import yaml

from triage.evidence import ROOT

STATUS = {"enum": ["draft", "approved"]}
NULLABLE_STR = {"type": ["string", "null"]}
PROVENANCE = {"version": {"type": "string", "pattern": "^v[0-9]+\\.[0-9]+$"}, "status": STATUS,
              "reviewed_by": NULLABLE_STR, "review_date": {"type": ["string", "null"], "format": "date"}}
FILE_REQUIRED = ["version", "status", "reviewed_by", "review_date"]
NUM_OR_NULL = {"type": ["number", "null"]}
RANGE = {"type": "array", "items": NUM_OR_NULL, "minItems": 2, "maxItems": 2}
YES_NO_OPTIONS = {"type": "array", "items": {"type": ["string", "object"]}, "minItems": 2}
REVIEW = {"type": "object", "required": ["status", "reviewed_by", "review_date"],
          "properties": {"status": STATUS, "reviewed_by": NULLABLE_STR, "review_date": NULLABLE_STR}}

RULES = {
    "type": "object", "required": FILE_REQUIRED + ["rules", "advice", "disclaimer"],
    "properties": {
        **PROVENANCE,
        "rules": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["id", "level", "when", "reason", "review"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "pattern": "^R[0-9]{2}[a-z]?_[a-z0-9_]+$"},
                "level": {"type": "string"}, "when": {"type": "object", "minProperties": 1, "maxProperties": 1},
                "action": {"type": "string"}, "wording_key": {"type": "string"},
                "reason": {"type": "string", "minLength": 10}, "review": REVIEW,
                "provenance": {"type": "object"},          # rule provenance card (templates/rule_provenance_card.yaml)
            }}},
        "advice": {"type": "object", "additionalProperties": {"type": "string"}},
        "wording": {"type": "object", "additionalProperties": {"type": "string"}},
        "disclaimer": {"type": "string", "minLength": 10},
    }}

MEASURE = {"type": "object", "required": ["unit", "measured_by", "normal", "urgent"],
           "properties": {"unit": {"type": "string"}, "measured_by": {"enum": ["kiosk", "device"]},
                          "normal": RANGE, "urgent": RANGE, "fever": {"type": "number"},
                          "sources": {"type": "array", "items": {"type": "string"}},
                          "adjust": {"type": "array", "items": {
                              "type": "object", "required": ["when"],
                              "properties": {"when": {"type": "object", "required": ["answer", "equals"]},
                                             "normal": RANGE, "urgent": RANGE, "note": {"type": "string"}}}}}}
RANGES = {
    "type": "object", "required": FILE_REQUIRED + ["min_quality", "required", "measures", "error_margins", "scope"],
    "properties": {
        **PROVENANCE,
        "scope": {"type": "object", "required": ["min_age", "max_age"],
                  "properties": {"min_age": {"type": "number"}, "max_age": {"type": "number"}}},
        "min_quality": {"type": "number", "minimum": 0, "maximum": 1},
        "required": {"type": "array", "items": {"type": "string"}},
        "measures": {"type": "object", "additionalProperties": MEASURE},
        "error_margins": {"type": "object", "required": ["status"], "properties": {
            "status": {"enum": ["placeholder", "measured"]}},
            "additionalProperties": {"type": ["object", "string"], "additionalProperties": {"type": "number",
                                                                                           "minimum": 0}}},
    }}

RED_FLAGS = {
    "type": "object", "required": FILE_REQUIRED + ["urgent_items", "items"],
    "properties": {
        **PROVENANCE,
        "urgent_items": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
        "items": {"type": "object", "additionalProperties": {
            "type": "object", "required": ["question", "complaint_regex"],
            "properties": {"question": {"type": "string", "minLength": 10},
                           "synonyms": {"type": "array", "items": {"type": "string"}},
                           "complaint_regex": {"type": "string"}}}},
    }}

ITEM = {"type": "object", "properties": {"question": {"type": "string"}, "options": YES_NO_OPTIONS,
                                         "type": {"enum": ["number"]}, "ask_if": {"type": "object"},
                                         "explains": {"type": "array"}, "effect": {"type": "string"}}}
QUESTIONNAIRE = {
    "type": "object", "required": FILE_REQUIRED + ["order", "sections", "scores", "persistent_days"],
    "properties": {
        **PROVENANCE,
        "persistent_days": {"type": "number", "minimum": 1},
        "order": {"type": "array", "items": {"type": "string"}},
        "sections": {"type": "object", "additionalProperties": {
            "type": "object", "required": ["items"],
            "properties": {"items": {"type": ["array", "object"]}, "options": YES_NO_OPTIONS,
                           "intro": {"type": "string"}}}},
        "scores": {"type": "object", "additionalProperties": {
            "type": "object", "required": ["items", "cutoff"],
            "properties": {"items": {"type": "array", "items": {"type": "string"}}, "cutoff": {"type": "number"}}}},
    }}

CONTACT = {"type": "object", "required": ["name", "number"],
           "properties": {"name": {"type": "string"}, "number": {"type": "string", "pattern": "^[0-9+ ]+$"}}}
CONTACTS = {"type": "object", "required": ["region", "verified", "verified_by", "verified_date", "emergency", "crisis"],
            "properties": {"region": {"type": "string"}, "verified": {"type": "boolean"},
                           "verified_by": NULLABLE_STR, "verified_date": NULLABLE_STR,
                           "emergency": {"type": "array", "items": CONTACT, "minItems": 1},
                           "crisis": {"type": "array", "items": CONTACT, "minItems": 1}}}

SCHEMAS = {"rules": RULES, "ranges": RANGES, "red_flags": RED_FLAGS, "questionnaire": QUESTIONNAIRE,
           "contacts": CONTACTS}

LEVEL = {"enum": ["URGENT", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE", "NOT_SUITABLE", None]}
VIGNETTE = {
    "type": "object", "required": ["id", "measurements", "answers", "clinician_labels"],
    "properties": {
        "id": {"type": "string"}, "age": {"type": ["number", "null"]}, "sex": NULLABLE_STR,
        "measurements": {"type": "object", "additionalProperties": {
            "anyOf": [{"type": ["number", "null"]}, {"type": "array", "items": {"type": "number"}, "minItems": 1}]}},
        "quality": {"type": "object", "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1}},
        "answers": {"type": "object", "additionalProperties": {"type": ["string", "number"]}},
        "scores": {"type": "object", "additionalProperties": {"type": "number"}},
        "flags": {"type": "array", "items": {"type": "string"}},
        "narrative": {"type": "string"},
        "clinician_labels": {"type": "object", "additionalProperties": LEVEL},
        "tags": {"type": "array", "items": {"type": "string"}},
    }}
EVIDENCE_COLUMNS = ["condition", "threshold_or_content", "source", "doi_or_url", "validated_population",
                    "reported_performance", "evidence_strength", "kiosk_caveat"]


def errors(schema, doc, where):
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [f"{where}/{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(doc)]


def validate_config(cfg):
    return [e for k, schema in SCHEMAS.items() for e in errors(schema, cfg[k], k)]


def validate_vignettes(vignettes, where="vignettes"):
    errs = [e for v in vignettes for e in errors(VIGNETTE, v, f"{where}/{v.get('id', '?')}")]
    ids = [v.get("id") for v in vignettes]
    return errs + [f"{where}: duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]


def validate_evidence_table(path=ROOT / "evidence" / "evidence_table.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return [f"{path.name}: empty"]
    errs = [f"{path.name}: missing column {c}" for c in EVIDENCE_COLUMNS if c not in rows[0]]
    return errs + [f"{path.name} row {i + 2}: empty {c}" for i, r in enumerate(rows) for c in ("condition", "source")
                   if not (r.get(c) or "").strip()]


if __name__ == "__main__":
    from triage.rules_engine import CONFIG_FILES, CONFIG
    cfg = {k: yaml.safe_load((CONFIG / f).read_text(encoding="utf-8")) for k, f in CONFIG_FILES.items()}
    errs = validate_config(cfg) + validate_evidence_table()
    for p in sorted((ROOT / "vignettes").glob("*.yaml")):
        errs += validate_vignettes(yaml.safe_load(p.read_text(encoding="utf-8")) or [], p.name)
    print("\n".join(errs) or "all configs, the evidence table and the vignettes are valid")
