"""Tests for what the triage starter kit added: the out-of-scope rule (R00), fever + unwell (R06a), the new red flags,
the new condition functions, the config / vignette / evidence-table schemas, and the kit's files."""
import copy

import pytest
import yaml

from conftest import build, session
from triage import rules_engine as re_
from triage.evidence import ROOT
from triage.schema import validate_config, validate_evidence_table, validate_vignettes


# ---------------------------------------------------------------- new condition functions

def test_answer_below_and_above(cfg):
    rec = build(cfg, answers={"age": 17})
    assert re_.answer_below(rec, cfg, "age", 18) == (True, ["Q1"])
    assert re_.answer_below(build(cfg, answers={"age": 18}), cfg, "age", 18)[0] is False      # strict
    assert re_.answer_above(build(cfg, answers={"age": 66}), cfg, "age", 65) == (True, ["Q1"])
    assert re_.answer_above(build(cfg, answers={"age": 65}), cfg, "age", 65)[0] is False
    assert re_.answer_below(build(cfg, answers={"age": "x"}), cfg, "age", 18)[0] is False     # not a number
    assert re_.answer_below(build(cfg), cfg, "age", 18)[0] is False                           # missing
    unconfirmed = build(cfg, answers={"age": (16, False)})
    assert re_.answer_below(unconfirmed, cfg, "age", 18)[0] is False
    assert re_.answer_below(unconfirmed, cfg, "age", 18, include_unconfirmed=True)[0] is True


@pytest.mark.parametrize("reps, margin, confirmed, expected", [
    ([38.5, 38.6], True, True, True),          # both >= 38.0 + 0.4
    ([38.4, 38.6], True, True, True),          # exactly at cut + margin counts
    ([38.3, 38.6], True, True, False),         # one reading within the margin
    ([38.1, 38.2], False, True, True),         # no margin: >= 38.0 is enough
    ([37.9, 38.2], False, True, False),
    ([38.6], True, True, False),               # a single reading cannot confirm
    ([38.6], True, False, True),
])
def test_measure_at_least(cfg, reps, margin, confirmed, expected):
    rec = build(cfg, {"temperature": {"repeat": reps, "margin": 0.4} if len(reps) > 1
                      else {"single": reps[0], "margin": 0.4}})
    assert re_.measure_at_least(rec, cfg, "temperature", 38.0, margin, confirmed)[0] is expected


def test_measure_at_least_ignores_other_measures(cfg):
    rec = build(cfg, {"heart_rate": 140})
    assert re_.measure_at_least(rec, cfg, "temperature", 38.0, False, False)[0] is False


# ---------------------------------------------------------------- R00 out of scope

@pytest.mark.parametrize("answers", [{"age": 17}, {"age": 66}, {"pregnant": "yes"}, {"pregnant": "not sure"},
                                     {"age": (15, False)}])                   # an unconfirmed age still counts
def test_out_of_scope(cfg, run, answers):
    d = run(session(cfg, answers=answers))
    assert (d["level"], d["rule_id"]) == ("NOT_SUITABLE", "R00_out_of_scope")
    assert "show_emergency_contacts" in d["actions"]


@pytest.mark.parametrize("age", [18, 40, 65])
def test_in_scope_ages(cfg, run, age):
    assert run(session(cfg, answers={"age": age, "pregnant": "no"}))["level"] == "SELF_CARE"


def test_red_flag_beats_out_of_scope(cfg, run):
    """Safety rule 3: a red flag refers even a user the check is not designed for."""
    d = run(session(cfg, answers={"age": 16, "chest_pain": "yes"}))
    assert (d["level"], d["rule_id"]) == ("URGENT", "R01_red_flag")
    assert "R00_out_of_scope" in [m["rule_id"] for m in d["also_matched"]]


def test_self_harm_beats_out_of_scope(cfg, run):
    rec = session(cfg, answers={"pregnant": "yes", "self_harm": "yes"})
    d = run(rec)
    assert d["level"] == "URGENT" and "show_crisis_contacts" in d["actions"]


def test_not_suitable_card_shows_emergency_number(cfg, run):
    rec = session(cfg, answers={"age": 70})
    run(rec)
    advice = rec["chain"][-1]
    assert advice["level"] == "NOT_SUITABLE"
    assert [c["number"] for c in advice["contacts"]] == [c["number"] for c in cfg["contacts"]["emergency"]]
    assert advice["text"] == cfg["rules"]["advice"]["NOT_SUITABLE"]


# ---------------------------------------------------------------- R06a fever + feeling unwell

FEVER = {"temperature": {"repeat": [38.6, 38.7], "margin": 0.4}}


def test_fever_and_unwell(cfg, run):
    d = run(session(cfg, FEVER, {"feeling_unwell": "yes"}))
    assert (d["level"], d["rule_id"]) == ("SEE_DOCTOR_SOON", "R06a_fever_unwell")


def test_fever_without_feeling_unwell_is_still_out_of_range(cfg, run):
    assert run(session(cfg, FEVER))["rule_id"] == "R06_vital_out"


def test_fever_unconfirmed_unwell_does_not_use_r06a(cfg, run):
    assert run(session(cfg, FEVER, {"feeling_unwell": ("yes", False)}))["rule_id"] == "R06_vital_out"


def test_temperature_just_below_fever_cut(cfg, run):
    rec = session(cfg, {"temperature": {"repeat": [37.9, 37.9], "margin": 0.4}}, {"feeling_unwell": "yes"})
    assert run(rec)["level"] == "SELF_CARE"


def test_very_high_fever_is_urgent_first(cfg, run):
    rec = session(cfg, {"temperature": {"repeat": [39.8, 39.9], "margin": 0.4}}, {"feeling_unwell": "yes"})
    assert run(rec)["rule_id"] == "R05_vital_far_out"


# ---------------------------------------------------------------- configs, schemas and kit files

def test_shipped_configs_pass_the_schema(cfg):
    assert validate_config(cfg) == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda c: c["rules"].pop("reviewed_by"), "reviewed_by"),
    (lambda c: c["rules"].update(status="final"), "status"),
    (lambda c: c["rules"]["rules"][0].pop("review"), "review"),
    (lambda c: c["rules"]["rules"][0].update(id="redflag"), "id"),
    (lambda c: c["ranges"]["measures"]["heart_rate"].update(normal=[60]), "normal"),
    (lambda c: c["ranges"].update(min_quality=2), "min_quality"),
    (lambda c: c["red_flags"]["items"]["chest_pain"].pop("complaint_regex"), "complaint_regex"),
    (lambda c: c["contacts"]["emergency"][0].update(number="call 112"), "number"),
    (lambda c: c["questionnaire"]["scores"]["PHQ2"].pop("cutoff"), "cutoff"),
])
def test_schema_rejects(cfg, mutate, needle):
    c = copy.deepcopy(cfg)
    mutate(c)
    errs = validate_config(c)
    assert errs and any(needle in e for e in errs), errs


def test_every_urgent_item_and_question_item_exists(cfg):
    items = cfg["red_flags"]["items"]
    assert set(cfg["red_flags"]["urgent_items"]) <= set(items)
    assert cfg["questionnaire"]["sections"]["red_flags"]["items"] == cfg["red_flags"]["urgent_items"]


def test_evidence_table_is_valid():
    assert validate_evidence_table() == []


def test_vignette_template_is_valid():
    from triage.bench.vignettes import normalise
    vig = [normalise(v) for v in yaml.safe_load((ROOT / "templates" / "vignette_template.yaml").read_text(encoding="utf-8"))]
    assert validate_vignettes(vig) == []
    assert validate_vignettes(vig + vig)[-1].endswith("duplicate id V001")


def test_knowledge_draft_has_the_kit_sections():
    from triage.followup_qa import load_knowledge
    k = load_knowledge(demo=True)
    for key in ("heart_rate_high", "crisis", "measurement_limits", "out_of_scope_questions"):
        assert k["sections"][key]
    assert k["status"] == "draft"
