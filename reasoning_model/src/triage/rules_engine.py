"""Triage rule engine: the ONLY place a triage level is decided. -> record["decision"]

Rules (configs/triage/rules.yaml) are ordered; the first rule whose `when` matches sets the level. A `when` is a
nested mapping built from the fixed condition functions in CONDITIONS plus all_of / any_of / not; nothing is eval'd.
Strings starting with `$` are references into the other configs ($red_flags.urgent_items, $ranges.min_quality).
Every condition returns (matched, evidence IDs that made it match), so the reasoning chain can cite M*/Q*/S* IDs.
Actions (show_crisis_contacts) are collected from every matching rule. record["wellness"] is never read here.

Reading a measurement against a range [lo, hi] (inclusive; null = open side) with error margin m:
    in          lo <= v <= hi                     (the clinician's range is not narrowed by the margin)
    borderline  outside, but by at most m         (could be a measurement error)
    out         v < lo - m  or  v > hi + m        (outside even if the device erred by m)
`margin: true` counts only `out` as outside; `margin: false` counts any reading outside the bare range.
`confirmed_repeat: true` needs >= 2 readings (repeat_values), all outside. A reading outside the range that is not
confirmed out (borderline, a single reading, or repeats that disagree) is re-measured once (R06b), never ignored, and
referred if it is still outside after that (R06c): "when in doubt, refer".
Answers: only confirmed answers count, unless `include_unconfirmed: true` (used for rules that refer, so a doubtful
"yes" still refers). `answer_equals` needs every confirmed answer to agree, so contradictory context answers never
relax a rule.

    python -m triage.rules_engine --describe          (from reasoning_model/src)
    python -m triage.rules_engine --approval          # what still blocks user tests
"""
import argparse
from pathlib import Path

import yaml

from triage.evidence import CONFIG

LEVELS = ["URGENT", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE", "REMEASURE"]
CONFIG_FILES = {"rules": "rules.yaml", "ranges": "vital_ranges.yaml", "red_flags": "red_flags.yaml",
                "questionnaire": "questionnaire.yaml", "contacts": "contacts.yaml"}


# ---------------------------------------------------------------- config

def load_config(folder=CONFIG):
    cfg = {k: yaml.safe_load((Path(folder) / f).read_text(encoding="utf-8")) for k, f in CONFIG_FILES.items()}
    errs = check_config(cfg)
    if errs:
        raise ValueError("invalid triage config:\n  " + "\n  ".join(errs))
    return cfg


def resolve(cfg, x):
    """'$red_flags.urgent_items' -> cfg['red_flags']['urgent_items']; anything else unchanged."""
    if not (isinstance(x, str) and x.startswith("$")):
        return x
    node = cfg
    for key in x[1:].split("."):
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"config reference {x} does not resolve")
        node = node[key]
    return node


def check_config(cfg):
    errs, rules = [], cfg["rules"]["rules"]
    ids = [r.get("id") for r in rules]
    errs += [f"duplicate rule id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for r in rules:
        if r.get("level") not in LEVELS:
            errs.append(f"{r.get('id')}: unknown level {r.get('level')}")
        if not r.get("reason"):
            errs.append(f"{r.get('id')}: needs a plain-language reason")
        if r.get("wording_key") and r["wording_key"] not in cfg["rules"].get("wording", {}):
            errs.append(f"{r['id']}: unknown wording_key {r['wording_key']}")
        if r.get("action") and r["action"] not in ACTIONS:
            errs.append(f"{r['id']}: unknown action {r['action']}")
        errs += [f"{r.get('id')}: {e}" for e in _check_cond(r.get("when"), cfg)]
    if rules and rules[-1].get("when") != {"always": {}}:
        errs.append("the last rule must be the default (when: {always: {}})")
    errs += [f"advice missing for level {lv}" for lv in LEVELS if lv not in cfg["rules"].get("advice", {})]
    for name, spec in cfg["ranges"]["measures"].items():
        (nlo, nhi), (ulo, uhi) = bounds(spec["normal"]), bounds(spec["urgent"])
        for kind, (lo, hi) in (("normal", (nlo, nhi)), ("urgent", (ulo, uhi))):
            if lo > hi:
                errs.append(f"{name}.{kind}: low {lo} > high {hi}")
        if not (ulo <= nlo and nhi <= uhi):
            errs.append(f"{name}: the normal range must lie inside the urgent range")
    return errs


def _check_cond(cond, cfg):
    if not (isinstance(cond, dict) and len(cond) == 1):
        return [f"condition must be a one-key mapping, got {cond!r}"]
    (name, params), = cond.items()
    if name in ("all_of", "any_of"):
        return [e for c in params for e in _check_cond(c, cfg)] if isinstance(params, list) and params \
            else [f"{name} needs a non-empty list"]
    if name == "not":
        return _check_cond(params, cfg)
    if name not in CONDITIONS:
        return [f"unknown condition {name}"]
    errs = []
    for k, v in (params or {}).items():
        try:
            v = resolve(cfg, v)
        except KeyError as e:
            errs.append(str(e.args[0]))
        if k == "value" and isinstance(v, bool):
            errs.append(f"{name}.value is a boolean: quote \"yes\"/\"no\" in YAML")
    return errs


# ---------------------------------------------------------------- evidence helpers

def _answers(rec, item, include_unconfirmed=False):
    return [a for a in rec["answers"] if a["item"] == item and (a["confirmed"] or include_unconfirmed)]


def _usable(rec):
    return [m for m in rec["measurements"] if m["value"] is not None]


def margin_for(m, cfg):
    if m.get("error_margin") is not None:
        return m["error_margin"]
    return cfg["ranges"]["error_margins"].get(m["source"], {}).get(m["name"], 0)


def range_for(name, kind, rec, cfg):
    """(range, adjustment or None); an `adjust` entry applies when its answer is confirmed and agrees."""
    spec = cfg["ranges"]["measures"].get(name)
    if spec is None:
        return None, None
    for adj in spec.get("adjust", []):
        if kind in adj and answer_equals(rec, cfg, adj["when"]["answer"], adj["when"]["equals"])[0]:
            return adj[kind], adj
    return spec[kind], None


def bounds(rng):
    """null in a range = open on that side (e.g. SpO2 has no upper limit)."""
    return (float("-inf") if rng[0] is None else rng[0]), (float("inf") if rng[1] is None else rng[1])


def reading_status(v, rng, margin):
    lo, hi = bounds(rng)
    if lo <= v <= hi:
        return "in"
    return "out" if v < lo - margin or v > hi + margin else "borderline"


def is_outside(v, rng, margin, use_margin):
    return reading_status(v, rng, margin) == "out" if use_margin else reading_status(v, rng, margin) != "in"


def readings(m):
    return m.get("repeat_values") or [m["value"]]


# ---------------------------------------------------------------- the fixed condition functions

def any_answer_in(rec, cfg, items, value, include_unconfirmed=False):
    hits = [a["id"] for i in items for a in _answers(rec, i, include_unconfirmed) if a["answer"] == value]
    return bool(hits), hits


def answer_equals(rec, cfg, item, value):
    ans = _answers(rec, item)
    ok = bool(ans) and all(a["answer"] == value for a in ans)
    return ok, [a["id"] for a in ans] if ok else []


def answer_at_least(rec, cfg, item, value, include_unconfirmed=False):
    hits = [a["id"] for a in _answers(rec, item, include_unconfirmed)
            if isinstance(a["answer"], (int, float)) and a["answer"] >= value]
    return bool(hits), hits


def score_at_least(rec, cfg, name, value):
    hits = [s["id"] for s in rec["scores"] if s["name"] == name and s["value"] >= value]
    return bool(hits), hits


def flag(rec, cfg, name):
    return name in rec["flags"], []


def any_low_quality(rec, cfg, min_quality):
    hits = [m["id"] for m in rec["measurements"] if m["quality"] < min_quality]
    return bool(hits), hits


def missing_measurement(rec, cfg, names):
    usable = {m["name"] for m in _usable(rec)}
    missing = [n for n in names if n not in usable]
    return bool(missing), [m["id"] for m in rec["measurements"] if m["name"] in missing]


def any_outside_range(rec, cfg, range, margin, confirmed_repeat):
    hits = []
    for m in _usable(rec):
        rng = range_for(m["name"], range, rec, cfg)[0]
        if rng is None:
            continue
        vals = readings(m) if confirmed_repeat else [m["value"]]
        outs = [is_outside(v, rng, margin_for(m, cfg), margin) for v in vals]
        if all(outs) and (len(vals) >= 2 or not confirmed_repeat):
            hits.append(m["id"])
    return bool(hits), hits


def any_unconfirmed_outside_range(rec, cfg, range):
    """Some reading is outside the bare range, but the measurement is not confirmed out (>= 2 readings, all beyond
    the error margin): borderline, a single reading, or disagreeing repeats."""
    hits = []
    for m in _usable(rec):
        rng = range_for(m["name"], range, rec, cfg)[0]
        if rng is None:
            continue
        st = [reading_status(v, rng, margin_for(m, cfg)) for v in readings(m)]
        if any(s != "in" for s in st) and not (len(st) >= 2 and all(s == "out" for s in st)):
            hits.append(m["id"])
    return bool(hits), hits


def always(rec, cfg):
    return True, []


CONDITIONS = {f.__name__: f for f in (any_answer_in, answer_equals, answer_at_least, score_at_least, flag,
                                      any_low_quality, missing_measurement, any_outside_range,
                                      any_unconfirmed_outside_range, always)}
ACTIONS = {"show_crisis_contacts"}


def evaluate(cond, rec, cfg):
    (name, params), = cond.items()
    if name in ("all_of", "any_of"):
        res = [evaluate(c, rec, cfg) for c in params]
        ok = all(r[0] for r in res) if name == "all_of" else any(r[0] for r in res)
        return ok, _dedupe([i for m, refs in res if m for i in refs]) if ok else []
    if name == "not":
        return not evaluate(params, rec, cfg)[0], []
    return CONDITIONS[name](rec, cfg, **{k: resolve(cfg, v) for k, v in (params or {}).items()})


def _dedupe(xs):
    return list(dict.fromkeys(xs))


# ---------------------------------------------------------------- decision

def decide(rec, cfg):
    matched = []
    for r in cfg["rules"]["rules"]:
        ok, refs = evaluate(r["when"], rec, cfg)
        if ok:
            matched.append((r, _dedupe(refs)))
    rule, refs = matched[0]  # the default rule always matches
    return {"level": rule["level"], "rule_id": rule["id"], "reason": rule["reason"], "refs": refs,
            "wording_key": rule.get("wording_key"),
            "actions": sorted({r["action"] for r, _ in matched if r.get("action")}),
            "also_matched": [{"rule_id": r["id"], "level": r["level"], "refs": x} for r, x in matched[1:]
                             if "always" not in r["when"]],
            "rules_status": cfg["rules"]["status"]}


def approval_problems(cfg):
    """Everything that must be signed off before the kiosk may run user tests (safety rule 2)."""
    probs = [f"{f}: status is {cfg[k].get('status')}" for k, f in CONFIG_FILES.items()
             if k != "contacts" and cfg[k].get("status") != "approved"]
    for r in cfg["rules"]["rules"]:
        rv = r.get("review") or {}
        if rv.get("status") != "approved" or not rv.get("reviewed_by") or not rv.get("review_date"):
            probs.append(f"rule {r['id']}: status {rv.get('status')}, reviewed_by {rv.get('reviewed_by')}, "
                         f"review_date {rv.get('review_date')}")
    if cfg["ranges"]["error_margins"].get("status") != "measured":
        probs.append("vital_ranges.yaml: error margins are placeholders, not the measured P6 values")
    if not cfg["contacts"].get("verified"):
        probs.append("contacts.yaml: numbers not verified")
    return probs


def require_approved(cfg):
    probs = approval_problems(cfg)
    if probs:
        raise RuntimeError("user tests blocked until the clinician sign-off is complete:\n  " + "\n  ".join(probs))


# ---------------------------------------------------------------- plain-text rule table

def describe(cond, cfg):
    (name, p), = cond.items()
    p = {k: resolve(cfg, v) for k, v in p.items()} if isinstance(p, dict) else p
    if name in ("all_of", "any_of"):
        return "(" + (" AND " if name == "all_of" else " OR ").join(describe(c, cfg) for c in p) + ")"
    if name == "not":
        return "NOT " + describe(p, cfg)
    unconf = " (unconfirmed answers count)" if p.get("include_unconfirmed") else ""
    return {
        "any_answer_in": lambda: f"answer '{p.get('value')}' to any of {', '.join(p.get('items', []))}{unconf}",
        "answer_equals": lambda: f"{p.get('item')} = '{p.get('value')}' (all confirmed answers)",
        "answer_at_least": lambda: f"{p.get('item')} >= {p.get('value')}{unconf}",
        "score_at_least": lambda: f"{p.get('name')} >= {p.get('value')}",
        "flag": lambda: f"flag '{p.get('name')}'",
        "any_low_quality": lambda: f"any measurement quality < {p.get('min_quality')}",
        "missing_measurement": lambda: f"missing or unmeasured: {', '.join(p.get('names', []))}",
        "any_outside_range": lambda: (f"any vital outside its {p.get('range')} range"
                                      + (" by more than the error margin" if p.get("margin") else "")
                                      + (" on >= 2 readings, all of them" if p.get("confirmed_repeat") else "")),
        "any_unconfirmed_outside_range": lambda: (f"any vital outside its {p.get('range')} range but not confirmed"
                                                  " (borderline, single reading, or repeats disagree)"),
        "always": lambda: "always",
    }[name]()


def rule_table(cfg):
    return [{"id": r["id"], "level": r["level"], "when": describe(r["when"], cfg),
             "status": (r.get("review") or {}).get("status")} for r in cfg["rules"]["rules"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--describe", action="store_true", help="print the rule table in plain text")
    ap.add_argument("--approval", action="store_true", help="list what blocks user tests")
    a = ap.parse_args()
    cfg = load_config()
    if a.describe or not a.approval:
        print(f"rules {cfg['rules']['version']} ({cfg['rules']['status']}); first match wins")
        for r in rule_table(cfg):
            print(f"{r['id']:<40} {r['level']:<16} {r['status']:<9} {r['when']}")
    if a.approval:
        print("\n".join(approval_problems(cfg)) or "all approved")
