"""One test per rule path plus the edge cases from the brief: boundary, boundary +- margin, missing value, low quality,
conflicting answers, disagreeing repeats, red flag over normal vitals, exercise + borderline -> REMEASURE -> decision."""
import copy

import pytest

from conftest import session


def remeasure(rec, **vitals):
    """What session.py will do after REMEASURE: new readings for the given vitals, then the `remeasured` flag."""
    rec = copy.deepcopy(rec)
    for m in rec["measurements"]:
        if m["name"] in vitals:
            m["repeat_values"] = vitals[m["name"]]
            m["value"] = sum(vitals[m["name"]]) / len(vitals[m["name"]])
            m["n_readings"] = len(vitals[m["name"]])
    rec["flags"].append("remeasured")
    rec["decision"] = rec["chain"] = None
    return rec


# ---------------------------------------------------------------- R01 red flags

@pytest.mark.parametrize("item", ["chest_pain", "severe_breathlessness", "fainting", "confusion",
                                  "sudden_weakness_numbness", "severe_headache"])
def test_red_flag_with_normal_vitals_is_urgent(cfg, run, item):
    d = run(session(cfg, answers={item: "yes"}))
    assert (d["level"], d["rule_id"]) == ("URGENT", "R01_red_flag")


def test_unconfirmed_red_flag_still_refers(cfg, run):
    assert run(session(cfg, answers={"chest_pain": ("yes", False)}))["rule_id"] == "R01_red_flag"


def test_conflicting_red_flag_answers_refer(cfg, run):
    rec = session(cfg, extra_answers=[("chest_pain", "yes", True)])                  # "no" earlier, then "yes"
    assert run(rec)["rule_id"] == "R01_red_flag"


def test_red_flag_overrides_low_quality(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [70, 70], "quality": 0.1}}, {"fainting": "yes"})
    assert run(rec)["level"] == "URGENT"


def test_red_flag_overrides_far_out_vital(cfg, run):
    d = run(session(cfg, {"heart_rate": 150}, {"chest_pain": "yes"}))
    assert d["rule_id"] == "R01_red_flag" and "R05_vital_far_out" in [m["rule_id"] for m in d["also_matched"]]


# ---------------------------------------------------------------- R02 self-harm

def test_self_harm_is_urgent_with_crisis_contacts(cfg, run):
    rec = session(cfg, answers={"self_harm": "yes"})
    d = run(rec)
    assert (d["level"], d["rule_id"], d["actions"]) == ("URGENT", "R02_self_harm", ["show_crisis_contacts"])
    numbers = [c["number"] for c in rec["chain"][-1]["contacts"]]
    assert "14416" in numbers and "112" in numbers


def test_crisis_contacts_shown_even_when_another_urgent_rule_wins(cfg, run):
    rec = session(cfg, answers={"self_harm": "yes", "chest_pain": "yes"})
    d = run(rec)
    assert d["rule_id"] == "R01_red_flag" and d["actions"] == ["show_crisis_contacts"]
    assert "14416" in [c["number"] for c in rec["chain"][-1]["contacts"]]


def test_unconfirmed_self_harm_still_refers(cfg, run):
    assert run(session(cfg, answers={"self_harm": ("yes", False)}))["rule_id"] == "R02_self_harm"


# ---------------------------------------------------------------- R03 quality

@pytest.mark.parametrize("vitals, flags", [
    ({"heart_rate": {"repeat": [70, 70], "quality": 0.3}}, []),          # low quality
    ({"temperature": {"repeat": [36.6, 36.6], "quality": 0.49}}, []),    # any measurement, not only HR
    ({"heart_rate": {"value": None, "quality": 0.0}}, []),               # required value missing
    ({}, ["face_not_found"]),
])
def test_retake(cfg, run, vitals, flags):
    d = run(session(cfg, vitals, flags=flags))
    assert (d["level"], d["rule_id"]) == ("RETAKE", "R03_quality")


def test_no_heart_rate_measurement_at_all_is_retake(cfg, run):
    rec = session(cfg)
    rec["measurements"] = [m for m in rec["measurements"] if m["name"] != "heart_rate"]
    assert run(rec)["rule_id"] == "R03_quality"


def test_quality_exactly_at_minimum_is_used(cfg, run):
    assert run(session(cfg, {"heart_rate": {"repeat": [72, 72], "quality": 0.5}}))["level"] == "SELF_CARE"


def test_missing_optional_measurement_is_not_retake(cfg, run):
    rec = session(cfg)
    rec["measurements"] = [m for m in rec["measurements"] if m["name"] != "temperature"]
    d = run(rec)
    assert d["level"] == "SELF_CARE"
    nm = [u for u in rec["chain"][4]["items"] if u["kind"] == "not_measured"][0]
    assert "temperature" in nm["names"]


def test_low_quality_beats_mood_screen(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [70, 70], "quality": 0.2}}, scores={"PHQ2": 5})
    assert run(rec)["level"] == "RETAKE"


# ---------------------------------------------------------------- R04 exercise -> REMEASURE -> decision

def test_exercise_borderline_remeasure_then_self_care(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [104, 106], "margin": 3}}, {"exercise_last_30min": "yes"})
    assert run(rec)["rule_id"] == "R04_recent_exercise_borderline"
    assert rec["chain"][-1]["level"] == "REMEASURE"
    d = run(remeasure(rec, heart_rate=[78, 80]))
    assert (d["level"], d["rule_id"]) == ("SELF_CARE", "R99_default")


def test_exercise_borderline_remeasure_still_out_refers(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [104, 106], "margin": 3}}, {"exercise_last_30min": "yes"})
    run(rec)
    d = run(remeasure(rec, heart_rate=[108, 110]))
    assert (d["level"], d["rule_id"]) == ("SEE_DOCTOR_SOON", "R06_vital_out")


def test_exercise_remeasure_happens_only_once(cfg, run):
    rec = remeasure(session(cfg, {"heart_rate": {"repeat": [104, 106], "margin": 3}},
                            {"exercise_last_30min": "yes"}), heart_rate=[104, 106])
    assert run(rec)["rule_id"] == "R06_vital_out"


def test_exercise_with_far_out_vital_is_remeasured_first(cfg, run):
    # brief's rule order: R04 precedes R05. Flagged for the clinician (see the review notes).
    rec = session(cfg, {"heart_rate": 150}, {"exercise_last_30min": "yes"})
    assert run(rec)["rule_id"] == "R04_recent_exercise_borderline"
    assert run(remeasure(rec, heart_rate=[150, 148]))["rule_id"] == "R05_vital_far_out"


def test_exercise_with_normal_vitals_is_self_care(cfg, run):
    assert run(session(cfg, answers={"exercise_last_30min": "yes"}))["level"] == "SELF_CARE"


@pytest.mark.parametrize("extra", [
    {"answers": {"exercise_last_30min": ("yes", False)}},                                    # unconfirmed
    {"answers": {"exercise_last_30min": "yes"}, "extra_answers": [("exercise_last_30min", "no", True)]},  # conflict
])
def test_unclear_exercise_answer_does_not_relax(cfg, run, extra):
    rec = session(cfg, {"heart_rate": {"repeat": [108, 108], "margin": 3}}, extra["answers"],
                  extra_answers=extra.get("extra_answers", ()))
    assert run(rec)["rule_id"] == "R06_vital_out"
    assert any(u["kind"] == "unclear_answer" for u in rec["chain"][4]["items"])


# ---------------------------------------------------------------- R05 far out

@pytest.mark.parametrize("vitals", [{"heart_rate": 140}, {"heart_rate": 38}, {"resp_rate": 26}, {"resp_rate": 8},
                                    {"temperature": 39.5}, {"temperature": 35.0}])
def test_far_out_vital_confirmed_is_urgent(cfg, run, vitals):
    d = run(session(cfg, vitals))
    assert (d["level"], d["rule_id"]) == ("URGENT", "R05_vital_far_out")


def test_urgent_boundary_uses_bare_value(cfg, run):
    assert run(session(cfg, {"heart_rate": {"repeat": [130, 130], "margin": 3}}))["rule_id"] == "R06_vital_out"
    assert run(session(cfg, {"heart_rate": {"repeat": [131, 131], "margin": 3}}))["rule_id"] == "R05_vital_far_out"


def test_device_vitals(cfg, run):
    assert run(session(cfg, {"spo2": {"repeat": [90, 91], "margin": 2}}))["rule_id"] == "R05_vital_far_out"
    assert run(session(cfg, {"spo2": {"repeat": [92, 92], "margin": 2}}))["rule_id"] == "R06_vital_out"
    assert run(session(cfg, {"spo2": {"repeat": [94, 94], "margin": 2}}))["rule_id"] == "R06b_vital_unconfirmed"
    assert run(session(cfg, {"sbp": {"repeat": [185, 190], "margin": 5}}))["rule_id"] == "R05_vital_far_out"
    assert run(session(cfg, {"spo2": {"repeat": [98, 99], "margin": 1}}))["level"] == "SELF_CARE"
    assert run(session(cfg, {"spo2": {"repeat": [100, 100], "margin": 2}}))["level"] == "SELF_CARE"  # open top


# ---------------------------------------------------------------- R06 out, with boundary and margin

@pytest.mark.parametrize("hr, margin, rule", [
    (100, 0, "R99_default"),              # exactly at the limit, no margin
    (101, 0, "R06_vital_out"),
    (97, 3, "R99_default"),               # limit - margin: the margin never narrows the range
    (100, 3, "R99_default"),              # exactly at the limit with a margin
    (101, 3, "R06b_vital_unconfirmed"),   # limit + less than the margin: borderline -> re-measure
    (103, 3, "R06b_vital_unconfirmed"),   # limit + margin
    (104, 3, "R06_vital_out"),            # beyond limit + margin on both readings -> refer
    (60, 0, "R99_default"),
    (59, 0, "R06_vital_out"),
    (57, 3, "R06b_vital_unconfirmed"),
    (56, 3, "R06_vital_out"),
])
def test_normal_range_boundaries(cfg, run, hr, margin, rule):
    assert run(session(cfg, {"heart_rate": {"repeat": [hr, hr], "margin": margin}}))["rule_id"] == rule


def test_athlete_low_heart_rate(cfg, run):
    slow = {"heart_rate": {"repeat": [50, 51], "margin": 3}}
    assert run(session(cfg, slow, {"athlete": "yes"}))["level"] == "SELF_CARE"
    assert run(session(cfg, slow))["rule_id"] == "R06_vital_out"
    assert run(session(cfg, slow, {"athlete": ("yes", False)}))["rule_id"] == "R06_vital_out"


# ---------------------------------------------------------------- R06b / R06c unconfirmed readings

@pytest.mark.parametrize("hr", [{"single": 110, "margin": 0}, {"repeat": [110, 92], "margin": 0}])
def test_unconfirmed_out_reading_is_remeasured(cfg, run, hr):
    d = run(session(cfg, {"heart_rate": hr}))
    assert (d["level"], d["rule_id"]) == ("REMEASURE", "R06b_vital_unconfirmed")


def test_still_unconfirmed_after_remeasure_refers(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [110, 92], "margin": 0}})
    run(rec)
    d = run(remeasure(rec, heart_rate=[109, 95, 96]))
    assert (d["level"], d["rule_id"]) == ("SEE_DOCTOR_SOON", "R06c_vital_unconfirmed_after_remeasure")


def test_unconfirmed_then_confirmed_urgent(cfg, run):
    rec = session(cfg, {"heart_rate": {"single": 150}})
    assert run(rec)["rule_id"] == "R06b_vital_unconfirmed"
    assert run(remeasure(rec, heart_rate=[150, 152]))["rule_id"] == "R05_vital_far_out"


def test_borderline_twice_is_remeasured_then_referred(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [102, 102], "margin": 3}})
    assert run(rec)["rule_id"] == "R06b_vital_unconfirmed"
    assert run(remeasure(rec, heart_rate=[102, 101]))["rule_id"] == "R06c_vital_unconfirmed_after_remeasure"


def test_unconfirmed_then_normal(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [110, 92], "margin": 0}})
    run(rec)
    assert run(remeasure(rec, heart_rate=[80, 82]))["level"] == "SELF_CARE"


# ---------------------------------------------------------------- R07 mood, R08 duration, R99 default

@pytest.mark.parametrize("scores, rule", [({"PHQ2": 3}, "R07_mood_screen"), ({"GAD2": 3}, "R07_mood_screen"),
                                          ({"PHQ2": 2, "GAD2": 2}, "R99_default")])
def test_mood_screen(cfg, run, scores, rule):
    rec = session(cfg, scores=scores)
    d = run(rec)
    assert d["rule_id"] == rule
    if rule == "R07_mood_screen":
        assert d["wording_key"] == "talk_to_professional"
        assert rec["chain"][-1]["text"] == cfg["rules"]["wording"]["talk_to_professional"]


def test_vital_out_beats_mood_screen(cfg, run):
    assert run(session(cfg, {"heart_rate": 110}, scores={"PHQ2": 4}))["rule_id"] == "R06_vital_out"


@pytest.mark.parametrize("days, rule", [(7, "R08_persistent_symptom"), (30, "R08_persistent_symptom"),
                                        (6, "R99_default")])
def test_persistent_symptom(cfg, run, days, rule):
    rec = session(cfg, answers={"has_symptom": "yes", "symptom_duration_days": days})
    assert run(rec)["rule_id"] == rule


def test_default_self_care_wording_is_fixed(cfg, run):
    rec = session(cfg)
    d = run(rec)
    assert (d["level"], d["rule_id"]) == ("SELF_CARE", "R99_default")
    adv = rec["chain"][-1]
    assert adv["text"] == "No warning signs were found by this check. If you feel unwell, see a doctor anyway."
    assert adv["disclaimer"] == "This check is informational and is not a medical diagnosis."
    assert adv["contacts"] == []


def test_missing_scores_do_not_fire_but_are_reported(cfg, run):
    rec = session(cfg)
    rec["scores"] = []
    assert run(rec)["level"] == "SELF_CARE"
    assert any(u["kind"] == "not_asked" for u in rec["chain"][4]["items"])


# ---------------------------------------------------------------- the wellness panel never changes the level (P7)

@pytest.mark.parametrize("base", [{}, {"vitals": {"heart_rate": 110}}, {"answers": {"chest_pain": "yes"}}])
def test_wellness_never_changes_the_level(cfg, run, base):
    plain = session(cfg, **base)
    levels = {run(copy.deepcopy(plain))["level"]}
    for w in ({"stress": "high", "probability_high": 0.99}, {"stress": "low"}, {"level": "URGENT"}, None):
        rec = copy.deepcopy(plain)
        rec["wellness"] = w
        levels.add(run(rec)["level"])
    assert len(levels) == 1
