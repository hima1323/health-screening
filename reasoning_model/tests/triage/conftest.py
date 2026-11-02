"""Shared fixtures for the triage tests, plus the rule-coverage table printed at the end of the run.

Every test that decides a level goes through the `run` fixture, which counts the rule that set the level. When the
whole triage suite runs, a rule that never fired fails the session (P0 'done when': 100% of rules covered).
"""
from collections import Counter
from statistics import mean

import pytest

from triage.evidence import add_answer, add_measurement, add_score, new_record
from triage.reasoning_chain import apply
from triage.rules_engine import load_config

FIRED = Counter()
UNITS = {"heart_rate": "bpm", "resp_rate": "/min", "temperature": "C", "spo2": "%", "sbp": "mmHg", "dbp": "mmHg"}
SOURCES = {"heart_rate": "rppg", "resp_rate": "thermal_nostril", "temperature": "thermal_canthus",
           "spo2": "device", "sbp": "device", "dbp": "device"}
NORMAL_VITALS = {"heart_rate": 72, "resp_rate": 14, "temperature": 36.6}
NO_ANSWERS = {i: "no" for i in ["chest_pain", "severe_breathlessness", "fainting", "confusion",
                                "sudden_weakness_numbness", "severe_headache", "exercise_last_30min",
                                "caffeine_last_2h", "feeling_ill", "athlete", "has_symptom", "self_harm"]}


@pytest.fixture(scope="session")
def cfg():
    return load_config()


def build(cfg, vitals=None, answers=None, scores=None, flags=(), extra_answers=()):
    """vitals: {name: v} -> two equal readings (the normal repeat); {name: {"repeat": [..]}} or {"single": v};
    optional "quality", "margin", "source" per vital; {"value": None} = could not be measured.
    answers: {item: answer} (confirmed) or {item: (answer, confirmed)}; extra_answers: [(item, answer, confirmed)]
    for duplicate / conflicting answers. scores: {"PHQ2": 1, ...}."""
    rec = new_record("test", cfg, code="test")
    for name, spec in (vitals or {}).items():
        spec = {"repeat": [spec, spec]} if isinstance(spec, (int, float)) else spec
        reps = spec.get("repeat")
        value = spec["single"] if "single" in spec else spec.get("value", mean(reps) if reps else None)
        add_measurement(rec, name, value, UNITS[name], spec.get("quality", 0.9), spec.get("source", SOURCES[name]),
                        spec.get("margin"), reps)
    for item, ans in (answers or {}).items():
        ans, ok = ans if isinstance(ans, tuple) else (ans, True)
        add_answer(rec, item, ans, ok)
    for item, ans, ok in extra_answers:
        add_answer(rec, item, ans, ok)
    for name, v in (scores or {}).items():
        add_score(rec, name, v)
    rec["flags"] = list(flags)
    return rec


def session(cfg, vitals=None, answers=None, scores=None, **kw):
    """A complete normal session with some parts overridden."""
    return build(cfg, {**NORMAL_VITALS, **(vitals or {})}, {**NO_ANSWERS, **(answers or {})},
                 {"PHQ2": 0, "GAD2": 0, **(scores or {})}, **kw)


@pytest.fixture
def run(cfg):
    def _run(rec):
        apply(rec, cfg)
        FIRED[rec["decision"]["rule_id"]] += 1
        return rec["decision"]
    return _run


def pytest_terminal_summary(terminalreporter):
    cfg = load_config()
    ids = [r["id"] for r in cfg["rules"]["rules"]]
    if not FIRED:
        return
    tr = terminalreporter
    tr.section("triage rule coverage (rule that set the level, per test decision)")
    tr.write_line(f"{'rule':<40} {'level':<16} {'decisions':>9}")
    for r in cfg["rules"]["rules"]:
        tr.write_line(f"{r['id']:<40} {r['level']:<16} {FIRED[r['id']]:>9}")
    covered = sum(FIRED[i] > 0 for i in ids)
    tr.write_line(f"covered {covered}/{len(ids)} rules ({100 * covered / len(ids):.0f}%)")


def pytest_sessionfinish(session, exitstatus):
    full_run = not session.config.option.keyword and not session.config.option.markexpr \
        and not any("::" in a for a in session.config.args)
    if full_run and FIRED and exitstatus == 0:
        missing = [r["id"] for r in load_config()["rules"]["rules"] if not FIRED[r["id"]]]
        if missing:
            print(f"\nrules never fired by any test: {missing}")
            session.exitstatus = 1
