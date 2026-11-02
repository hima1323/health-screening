"""Unit tests for every fixed condition function, the range reading, config references and config checks."""
import copy

import pytest

from conftest import build
from triage import rules_engine as re_
from triage.rules_engine import (CONDITIONS, approval_problems, check_config, evaluate, reading_status,
                                 require_approved, resolve)


def test_every_condition_function_is_tested():
    tested = {"any_answer_in", "answer_equals", "answer_at_least", "score_at_least", "flag", "any_low_quality",
              "missing_measurement", "any_outside_range", "any_unconfirmed_outside_range", "always"}
    assert set(CONDITIONS) == tested


# ---------------------------------------------------------------- range reading: boundary and margin

@pytest.mark.parametrize("v, margin, status", [
    (100, 0, "in"),            # exactly at the upper limit: inside (inclusive)
    (100.1, 0, "out"),         # no margin: any step outside is out
    (60, 0, "in"),             # exactly at the lower limit
    (59.9, 0, "out"),
    (97, 3, "in"),             # limit - margin: the margin never narrows the range
    (100, 3, "in"),            # at the limit with a margin
    (101, 3, "borderline"),    # outside, within the margin
    (103, 3, "borderline"),    # limit + margin: could still be a measurement error
    (103.5, 3, "out"),         # beyond limit + margin
    (62, 3, "in"),
    (57, 3, "borderline"),     # limit - margin
    (56.9, 3, "out"),
])
def test_reading_status(v, margin, status):
    assert reading_status(v, [60, 100], margin) == status


# ---------------------------------------------------------------- answers

def test_any_answer_in(cfg):
    rec = build(cfg, answers={"chest_pain": "no", "fainting": ("yes", False)})
    assert re_.any_answer_in(rec, cfg, ["chest_pain", "fainting"], "yes") == (False, [])
    assert re_.any_answer_in(rec, cfg, ["chest_pain", "fainting"], "yes", include_unconfirmed=True) == (True, ["Q2"])
    assert re_.any_answer_in(rec, cfg, ["confusion"], "yes", True) == (False, [])          # not asked


def test_answer_equals_needs_all_confirmed_answers_to_agree(cfg):
    assert re_.answer_equals(build(cfg, answers={"athlete": "yes"}), cfg, "athlete", "yes") == (True, ["Q1"])
    assert re_.answer_equals(build(cfg, answers={"athlete": ("yes", False)}), cfg, "athlete", "yes")[0] is False
    conflict = build(cfg, answers={"athlete": "yes"}, extra_answers=[("athlete", "no", True)])
    assert re_.answer_equals(conflict, cfg, "athlete", "yes")[0] is False
    assert re_.answer_equals(build(cfg), cfg, "athlete", "yes")[0] is False                 # missing


def test_answer_at_least(cfg):
    rec = build(cfg, answers={"symptom_duration_days": 7})
    assert re_.answer_at_least(rec, cfg, "symptom_duration_days", 7) == (True, ["Q1"])
    assert re_.answer_at_least(rec, cfg, "symptom_duration_days", 8)[0] is False
    text = build(cfg, answers={"symptom_duration_days": "a week"})                            # not a number
    assert re_.answer_at_least(text, cfg, "symptom_duration_days", 7)[0] is False
    unconf = build(cfg, answers={"symptom_duration_days": (9, False)})
    assert re_.answer_at_least(unconf, cfg, "symptom_duration_days", 7)[0] is False
    assert re_.answer_at_least(unconf, cfg, "symptom_duration_days", 7, include_unconfirmed=True)[0] is True


def test_score_at_least(cfg):
    rec = build(cfg, scores={"PHQ2": 3, "GAD2": 2})
    assert re_.score_at_least(rec, cfg, "PHQ2", 3) == (True, ["S1"])
    assert re_.score_at_least(rec, cfg, "GAD2", 3) == (False, [])
    assert re_.score_at_least(build(cfg), cfg, "PHQ2", 3) == (False, [])                     # not asked


def test_flag(cfg):
    assert re_.flag(build(cfg, flags=["face_not_found"]), cfg, "face_not_found") == (True, [])
    assert re_.flag(build(cfg), cfg, "face_not_found") == (False, [])


# ---------------------------------------------------------------- measurements

def test_any_low_quality(cfg):
    rec = build(cfg, {"heart_rate": {"repeat": [70, 70], "quality": 0.49}, "resp_rate": {"repeat": [14, 14],
                                                                                         "quality": 0.5}})
    assert re_.any_low_quality(rec, cfg, 0.5) == (True, ["M1"])                              # 0.5 itself is fine


def test_missing_measurement(cfg):
    assert re_.missing_measurement(build(cfg, {"resp_rate": 14}), cfg, ["heart_rate"]) == (True, [])
    assert re_.missing_measurement(build(cfg, {"heart_rate": {"value": None}}), cfg, ["heart_rate"]) == (True, ["M1"])
    assert re_.missing_measurement(build(cfg, {"heart_rate": 70}), cfg, ["heart_rate"]) == (False, [])


def test_any_outside_range_confirmed_repeat(cfg):
    out2 = build(cfg, {"heart_rate": {"repeat": [110, 108], "margin": 0}})
    assert re_.any_outside_range(out2, cfg, "normal", True, True) == (True, ["M1"])
    one = build(cfg, {"heart_rate": {"single": 110, "margin": 0}})
    assert re_.any_outside_range(one, cfg, "normal", True, True)[0] is False                 # no repeat -> unconfirmed
    assert re_.any_outside_range(one, cfg, "normal", True, False)[0] is True
    split = build(cfg, {"heart_rate": {"repeat": [110, 90], "margin": 0}})
    assert re_.any_outside_range(split, cfg, "normal", True, True)[0] is False


def test_any_outside_range_margin_flag(cfg):
    rec = build(cfg, {"heart_rate": {"repeat": [102, 102], "margin": 3}})
    assert re_.any_outside_range(rec, cfg, "normal", True, True)[0] is False                 # borderline is not out
    assert re_.any_outside_range(rec, cfg, "normal", False, True)[0] is True                 # bare value outside


def test_any_outside_range_skips_unmeasured_and_unknown(cfg):
    rec = build(cfg, {"heart_rate": {"value": None}})
    rec["measurements"].append({"id": "M2", "name": "glucose", "value": 999, "unit": "mg/dl", "quality": 1.0,
                                "source": "device"})
    assert re_.any_outside_range(rec, cfg, "normal", True, False) == (False, [])


def test_record_margin_overrides_config_margin(cfg):
    rec = build(cfg, {"heart_rate": {"repeat": [104, 104], "margin": 1}})                   # config rppg margin is 5
    assert re_.any_outside_range(rec, cfg, "normal", True, True)[0] is True
    rec = build(cfg, {"heart_rate": {"repeat": [104, 104]}})
    assert re_.any_outside_range(rec, cfg, "normal", True, True)[0] is False


def test_any_unconfirmed_outside_range(cfg):
    unconf = lambda hr: re_.any_unconfirmed_outside_range(build(cfg, {"heart_rate": hr}), cfg, "normal")
    assert unconf({"single": 110, "margin": 0}) == (True, ["M1"])                            # single reading
    assert unconf({"repeat": [110, 90], "margin": 0}) == (True, ["M1"])                      # repeats disagree
    assert unconf({"repeat": [102, 102], "margin": 3}) == (True, ["M1"])                     # borderline twice
    assert unconf({"repeat": [102, 110], "margin": 3})[0] is True                            # borderline + out
    assert unconf({"repeat": [110, 108], "margin": 0})[0] is False                           # confirmed out
    assert unconf({"repeat": [80, 82], "margin": 0})[0] is False                             # inside


def test_athlete_adjusts_heart_rate_range(cfg):
    athlete = build(cfg, {"heart_rate": {"repeat": [50, 50], "margin": 3}}, {"athlete": "yes"})
    assert re_.any_outside_range(athlete, cfg, "normal", True, True)[0] is False
    other = build(cfg, {"heart_rate": {"repeat": [50, 50], "margin": 3}}, {"athlete": "no"})
    assert re_.any_outside_range(other, cfg, "normal", True, True)[0] is True


def test_always(cfg):
    assert re_.always(build(cfg), cfg) == (True, [])


# ---------------------------------------------------------------- combinators and references

def test_combinators(cfg):
    rec = build(cfg, answers={"chest_pain": "yes"}, scores={"PHQ2": 1}, flags=["remeasured"])
    yes = {"any_answer_in": {"items": ["chest_pain"], "value": "yes"}}
    no = {"score_at_least": {"name": "PHQ2", "value": 3}}
    assert evaluate({"all_of": [yes, {"flag": {"name": "remeasured"}}]}, rec, cfg) == (True, ["Q1"])
    assert evaluate({"all_of": [yes, no]}, rec, cfg) == (False, [])
    assert evaluate({"any_of": [no, yes]}, rec, cfg) == (True, ["Q1"])
    assert evaluate({"any_of": [no, no]}, rec, cfg) == (False, [])
    assert evaluate({"not": no}, rec, cfg) == (True, [])
    assert evaluate({"not": yes}, rec, cfg) == (False, [])


def test_resolve(cfg):
    assert resolve(cfg, "$ranges.min_quality") == 0.5
    assert "chest_pain" in resolve(cfg, "$red_flags.urgent_items")
    assert resolve(cfg, "plain") == "plain"
    with pytest.raises(KeyError):
        resolve(cfg, "$ranges.no_such_key")


# ---------------------------------------------------------------- config checks and the approval gate

def _bad(cfg, mutate):
    c = copy.deepcopy(cfg)
    mutate(c)
    return check_config(c)


def test_shipped_config_is_valid(cfg):
    assert check_config(cfg) == []


def test_check_config_rejects_bad_tables(cfg):
    rules = lambda c: c["rules"]["rules"]
    assert any("unknown condition" in e for e in _bad(cfg, lambda c: rules(c)[0].update(when={"eval": "1"})))
    assert any("boolean" in e for e in _bad(cfg, lambda c: rules(c)[0]["when"]["any_answer_in"].update(value=True)))
    assert any("does not resolve" in e for e in _bad(cfg, lambda c: rules(c)[2]["when"]["any_of"][0]
                                                     ["any_low_quality"].update(min_quality="$ranges.nope")))
    assert any("unknown level" in e for e in _bad(cfg, lambda c: rules(c)[0].update(level="MAYBE")))
    assert any("last rule" in e for e in _bad(cfg, lambda c: rules(c).pop()))
    assert any("duplicate" in e for e in _bad(cfg, lambda c: rules(c).append(dict(rules(c)[-1]))))
    assert any("inside the urgent" in e for e in _bad(cfg, lambda c: c["ranges"]["measures"]["heart_rate"]
                                                      .update(normal=[30, 100])))
    assert any("unknown action" in e for e in _bad(cfg, lambda c: rules(c)[1].update(action="call_someone")))


def test_draft_config_blocks_user_tests(cfg):
    with pytest.raises(RuntimeError, match="user tests blocked"):
        require_approved(cfg)


def test_fully_approved_config_passes_gate(cfg):
    c = copy.deepcopy(cfg)
    for k in ("rules", "ranges", "red_flags", "questionnaire"):
        c[k]["status"] = "approved"
    for r in c["rules"]["rules"]:
        r["review"] = {"status": "approved", "reviewed_by": "Dr Test", "review_date": "2026-11-01"}
    c["ranges"]["error_margins"]["status"] = "measured"
    c["contacts"]["verified"] = True
    assert approval_problems(c) == []
    require_approved(c)
    c["rules"]["rules"][3]["review"]["reviewed_by"] = None                                   # one rule unsigned
    assert len(approval_problems(c)) == 1
