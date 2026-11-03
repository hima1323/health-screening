"""Phase E3/E4 tests: 21 scripted end-to-end sessions (expected level, rule and chain), the questionnaire, the verifier,
the deterministic explanation template and the follow-up Q&A routing. No LLM: the template and fixed texts are used
(the LLM path is measured by bench/reasoning_bench.py)."""
import copy

import pytest

from conftest import FIRED, session
from triage import questionnaire as qn
from triage.explainer import explain, render_template
from triage.followup_qa import answer, load_knowledge, route
from triage.session import Session, scripted
from triage.verify import (check_digits, check_placeholders, forbidden_terms, level_conflicts, verify_answer,
                           verify_explanation)

NORMAL = {"heart_rate": [72, 74], "resp_rate": [14, 15], "temperature": [36.6, 36.7]}
PHQ_HIGH = {"phq2_1": "Nearly every day", "phq2_2": "More than half the days"}

# (name, script, expected status / level, expected rule, extra check on the result)
SCRIPTS = [
    ("all normal", {"vitals": NORMAL}, "SELF_CARE", "R99_default", None),
    ("no consent", {"answers": {"consent": "no"}, "vitals": NORMAL}, "no_consent", None, None),
    ("consent not confirmed", {"answers": {"consent": ["yes", False]}, "vitals": NORMAL}, "no_consent", None, None),
    ("age 16", {"answers": {"age": 16}, "vitals": NORMAL}, "NOT_SUITABLE", "R00_out_of_scope",
     lambda r: r["record"]["measurements"] == []),
    ("age 16 with chest pain", {"answers": {"age": 16, "chest_pain": "yes"}, "vitals": NORMAL}, "URGENT",
     "R01_red_flag", lambda r: r["record"]["measurements"] == []),
    ("pregnant with self-harm thoughts", {"answers": {"pregnant": "yes", "self_harm": "yes"}, "vitals": NORMAL},
     "URGENT", "R02_self_harm", lambda r: "show_crisis_contacts" in r["record"]["decision"]["actions"]),
    ("chest pain, normal vitals", {"answers": {"chest_pain": "yes"}, "vitals": NORMAL}, "URGENT", "R01_red_flag",
     None),
    ("self-harm", {"answers": {"self_harm": "yes"}, "vitals": NORMAL}, "URGENT", "R02_self_harm",
     lambda r: len(r["card"]["contacts"]) == 2),
    ("face not found", {"vitals": NORMAL, "flags": ["face_not_found"]}, "RETAKE", "R03_quality", None),
    ("heart rate not measured", {"vitals": {**NORMAL, "heart_rate": None}}, "RETAKE", "R03_quality", None),
    ("low quality", {"vitals": NORMAL, "quality": {"heart_rate": 0.4}}, "RETAKE", "R03_quality", None),
    ("exercise, borderline, fine after rest",
     {"answers": {"exercise_last_30min": "yes"}, "vitals": {**NORMAL, "heart_rate": [106, 104]},
      "vitals_after_rest": NORMAL}, "SELF_CARE", "R99_default",
     lambda r: [e["round"] for e in r["events"] if e["step"] == "measure"] == [1, 2]
     and "remeasured" in r["record"]["flags"]),
    ("exercise, still high after rest",
     {"answers": {"exercise_last_30min": "yes"}, "vitals": {**NORMAL, "heart_rate": [112, 110]},
      "vitals_after_rest": {**NORMAL, "heart_rate": [112, 110]}}, "SEE_DOCTOR_SOON", "R06_vital_out", None),
    ("very fast heart rate", {"vitals": {**NORMAL, "heart_rate": [150, 148]}}, "URGENT", "R05_vital_far_out", None),
    ("fever and unwell", {"answers": {"feeling_unwell": "yes"}, "vitals": {**NORMAL, "temperature": [38.7, 38.8]}},
     "SEE_DOCTOR_SOON", "R06a_fever_unwell", None),
    ("disagreeing repeats, still borderline after rest",
     {"vitals": {**NORMAL, "heart_rate": [103, 99]}, "vitals_after_rest": {**NORMAL, "heart_rate": [102, 104]}},
     "SEE_DOCTOR_SOON", "R06c_vital_unconfirmed_after_remeasure", None),
    ("mood screen", {"answers": PHQ_HIGH, "vitals": NORMAL}, "SEE_DOCTOR_SOON", "R07_mood_screen",
     lambda r: any(s["name"] == "PHQ2" and s["value"] == 5 for s in r["record"]["scores"])),
    ("persistent symptom", {"answers": {"has_symptom": "yes", "symptom_duration_days": 10}, "vitals": NORMAL},
     "SEE_DOCTOR_SOON", "R08_persistent_symptom", None),
    ("no symptom: duration not asked", {"vitals": NORMAL}, "SELF_CARE", "R99_default",
     lambda r: all(a["item"] != "symptom_duration_days" for a in r["record"]["answers"])),
    ("athlete, slow heart rate", {"answers": {"athlete": "yes"}, "vitals": {**NORMAL, "heart_rate": [52, 53]}},
     "SELF_CARE", "R99_default", None),
    ("unconfirmed chest pain still refers", {"answers": {"chest_pain": ["yes", False]}, "vitals": NORMAL}, "URGENT",
     "R01_red_flag", None),
]


@pytest.mark.parametrize("name, script, level, rule, check", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_scripted_session(cfg, name, script, level, rule, check):
    measure, ask = scripted(script)
    res = Session(cfg, measure, ask, demo=True, use_llm=False, log=False).run()
    if level == "no_consent":
        assert res["status"] == "no_consent" and "record" not in res
        return
    FIRED[res["rule_id"]] += 1
    assert (res["level"], res["rule_id"]) == (level, rule)
    chain = {s["step"]: s for s in res["record"]["chain"]}
    assert chain["rule"]["rule_id"] == rule and chain["advice"]["level"] == level
    assert res["card"]["level"] == level and res["card"]["text_source"] == "template"
    if check:
        assert check(res)


def test_user_session_needs_approved_config(cfg):
    measure, ask = scripted({"vitals": NORMAL})
    with pytest.raises(RuntimeError, match="user tests blocked"):
        Session(cfg, measure, ask)


def test_session_log_is_written(cfg, tmp_path, monkeypatch):
    import triage.session as S
    monkeypatch.setattr(S, "LOGS", tmp_path)
    measure, ask = scripted({"vitals": NORMAL})
    res = Session(cfg, measure, ask, demo=True, use_llm=False).run()
    assert (tmp_path / f"{res['session_id']}.json").exists() and res["session_id"].startswith("demo-")


# ---------------------------------------------------------------- questionnaire

def test_question_order_and_sources(cfg):
    qs = qn.questions(cfg)
    sections = [q["section"] for q in qs]
    assert sections.index("consent") < sections.index("scope") < sections.index("red_flags") \
        < sections.index("context") < sections.index("duration") < sections.index("mood")
    by = {q["item"]: q for q in qs}
    assert by["chest_pain"]["question"] == cfg["red_flags"]["items"]["chest_pain"]["question"]
    assert by["self_harm"]["question"] == cfg["red_flags"]["items"]["self_harm"]["question"]
    assert qs[-1]["item"] == "self_harm"
    assert by["phq2_1"]["options"][3] == "Nearly every day"


def test_ask_if_and_scores(cfg):
    assert "symptom_duration_days" not in [q["item"] for q in qn.pending(cfg, {"has_symptom": "no"})]
    assert "symptom_duration_days" in [q["item"] for q in qn.pending(cfg, {"has_symptom": "yes"})]
    assert qn.scores(cfg, {"phq2_1": 2, "phq2_2": 1}) == {"PHQ2": 3}
    assert qn.scores(cfg, {"phq2_1": 2}) == {}                                   # incomplete -> no score


def test_unconfirmed_mood_answers_give_no_score(cfg):
    rec = session(cfg)
    rec["answers"], rec["scores"] = [], []
    qn.record_answers(rec, cfg, {"phq2_1": "Nearly every day", "phq2_2": "Nearly every day"}, unconfirmed={"phq2_1"})
    assert rec["scores"] == []


@pytest.mark.parametrize("item, text, option", [
    ("chest_pain", "yes, my chest feels heavy", "yes"),
    ("chest_pain", "I have chest tightness", "yes"),
    ("chest_pain", "no chest pain at all", "no"),
    ("chest_pain", "I don't know", None),                 # 'no' inside 'know' must not count
    ("phq2_1", "several days I guess", "Several days"),
    ("symptom_duration_days", "about 12 days", 12),
    ("pregnant", "not sure", "not sure"),
    ("exercise_last_30min", "nope", "no"),
])
def test_free_text_mapping(cfg, item, text, option):
    q = next(q for q in qn.questions(cfg) if q["item"] == item)
    assert qn.map_free_text(cfg, q, text)["option"] == option


# ---------------------------------------------------------------- verifier

def test_verifier_checks(cfg):
    rec = session(cfg, {"heart_rate": {"repeat": [110, 112]}}, {"caffeine_last_2h": "yes"})
    from triage.reasoning_chain import apply
    apply(rec, cfg)
    assert check_placeholders("{M1.value} {M1.unit}", rec) == []
    assert check_placeholders("{M9.value}", rec) and check_placeholders("{heart_rate}", rec)
    assert check_digits("about 110 bpm") and not check_digits("{M1.value} bpm")
    assert forbidden_terms("You may have tachycardia; take 500 mg paracetamol") == ["tachycardia", "paracetamol",
                                                                                      "mg"]
    assert forbidden_terms("You don't need a doctor.")
    assert not forbidden_terms("Your heart rate was above the usual range.")
    assert level_conflicts("This is an emergency", "SEE_DOCTOR_SOON")
    assert not level_conflicts("Please see a doctor in the next few days", "SEE_DOCTOR_SOON")
    good = {"summary": "Your heart rate was high.", "reasons": [{"id": rec["decision"]["rule_id"], "text": "x"}],
            "uncertainty": "", "next_step": "See a doctor."}
    assert verify_explanation(good, rec) == []
    assert any("must include the rule" in e for e in verify_explanation({**good, "reasons": []}, rec))
    assert verify_answer("It was {M1.value}.", rec, ["a"], ["b"])                 # cites a source not given


def test_template_passes_verifier_for_every_rule(cfg, run):
    cases = [session(cfg), session(cfg, answers={"chest_pain": "yes"}), session(cfg, answers={"self_harm": "yes"}),
             session(cfg, {"heart_rate": {"repeat": [70, 70], "quality": 0.1}}),
             session(cfg, {"heart_rate": {"repeat": [104, 106]}}, {"exercise_last_30min": "yes"}),
             session(cfg, {"heart_rate": {"repeat": [150, 152]}}), session(cfg, answers={"age": 80}),
             session(cfg, scores={"PHQ2": 4})]
    for rec in cases:
        run(rec)
        assert verify_explanation(render_template(rec, cfg), rec) == [], rec["decision"]["rule_id"]
        card, log = explain(rec, cfg, use_llm=False)
        assert card["level"] == rec["decision"]["level"] and card["disclaimer"] == cfg["rules"]["disclaimer"]


def test_card_contacts(cfg, run):
    rec = session(cfg, answers={"self_harm": "yes"})
    run(rec)
    card, _ = explain(rec, cfg, use_llm=False)
    numbers = [c["number"] for c in card["contacts"]]
    assert all(c["number"] in numbers for c in cfg["contacts"]["crisis"] + cfg["contacts"]["emergency"])


# ---------------------------------------------------------------- follow-up Q&A (routing and fixed texts)

@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(demo=True)


def test_knowledge_needs_approval_outside_demo():
    with pytest.raises(RuntimeError, match="demo mode"):
        load_knowledge(demo=False)


@pytest.mark.parametrize("question, first", [
    ("should I take ibuprofen?", "out_of_scope_questions"),
    ("Do I have an infection?", "out_of_scope_questions"),
    ("I sometimes think I'd be better off dead", "crisis"),
    ("I feel like hurting myself", "crisis"),
    ("what number do I call?", "contacts"),
    ("does coffee change the reading?", "heart_rate_high"),
    ("why did you measure me twice", "why_repeated"),
    ("is my breathing ok?", "breathing_fast"),
    ("can the camera measure blood pressure?", "measurement_limits"),
    ("what's the weather tomorrow", "off_topic"),
])
def test_routing(cfg, run, question, first):
    rec = session(cfg)
    run(rec)
    assert route(question, rec)[0] == first


def test_fixed_answers_never_use_the_llm(cfg, run, knowledge):
    rec = session(cfg, answers={"self_harm": "yes"})
    run(rec)
    res = answer("I want to hurt myself", rec, cfg, knowledge, use_llm=True)
    assert res["by"] == "fixed" and "14416" in res["answer"] and "112" in res["answer"]
    assert answer("what dose should I take", rec, cfg, knowledge)["by"] == "fixed"


def test_result_question_follows_the_level(cfg, run, knowledge):
    rec = session(cfg, {"heart_rate": {"repeat": [112, 114]}})
    run(rec)
    res = answer("what should I do now?", rec, cfg, knowledge, use_llm=False)
    assert res["sources"] == ["result_see_doctor_soon"]


def test_verifier_catches_wrong_high_low_claims(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [86, 86]}, "resp_rate": {"repeat": [17, 17]}})
    run(rec)
    from triage.verify import reading_claims
    assert reading_claims("You have a high heart rate and your breathing rate is within normal limits.", rec) == \
        ["the text calls the heart rate high, but it was within the usual range"]
    assert reading_claims("Your heart rate was within the usual range.", rec) == []
    assert reading_claims("Recent exercise can raise heart rate.", rec) == []
    fast = session(cfg, {"heart_rate": {"repeat": [118, 120]}})
    run(fast)
    assert reading_claims("Your pulse was fast, above the usual range.", fast) == []
    assert reading_claims("Your heart rate was low.", fast)


def test_template_passes_for_every_demo_sample(cfg):
    """The Aura demo samples (built locally, git-ignored) must never fall over in the template path."""
    from triage.demo_samples import load_samples
    from triage.demo_service import run_sample
    samples = load_samples()
    if not samples:
        pytest.skip("no demo samples built (python -m triage.demo_samples --build)")
    for sid, s in samples.items():
        r = run_sample(s, use_llm=False)
        assert r["text_source"] == "template" and r["level"], sid
        assert not any("template:" in e for errs in [] for e in errs)
        assert verify_explanation(render_template(*_rec(s, cfg)), _rec(s, cfg)[0]) == [], sid


def _rec(sample, cfg):
    import pandas as pd
    from triage.bench import dataset_bench as DB
    from triage.bench.vignettes import to_record
    from triage.reasoning_chain import apply
    rec = apply(to_record(DB.to_vignettes(pd.DataFrame([sample["case"]]), cfg)[0][0], cfg), cfg)
    if rec["decision"]["level"] == "REMEASURE":
        rec = apply(to_record(DB.to_vignettes(pd.DataFrame([sample["case"]]), cfg)[0][0], cfg, after_rest=True), cfg)
    return rec, cfg
