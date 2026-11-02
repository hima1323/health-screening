"""Reasoning chain structure, its references into the evidence record, and the evidence schema."""
import pytest

from conftest import build, session
from triage.evidence import add_answer, by_id, validate

STEPS = ["evidence", "interpretation", "context", "rule", "uncertainty", "advice"]


def _refs(chain):
    """Every evidence ID mentioned anywhere in the chain."""
    out = set()
    def walk(x, key=None):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif isinstance(x, str) and key in ("ref", "refs", "could_explain", "measurements", "answers", "scores"):
            out.add(x)
    walk(chain)
    return out


@pytest.mark.parametrize("kw", [{}, {"vitals": {"heart_rate": 110}}, {"answers": {"self_harm": "yes"}},
                                {"vitals": {"heart_rate": {"single": 120}}}, {"flags": ["face_not_found"]},
                                {"answers": {"exercise_last_30min": "yes"}, "vitals": {"heart_rate": 108}}])
def test_chain_shape_refs_and_schema(cfg, run, kw):
    rec = session(cfg, **kw)
    d = run(rec)
    assert [s["step"] for s in rec["chain"]] == STEPS
    assert _refs(rec["chain"]) <= set(by_id(rec))                     # no dangling IDs
    assert set(d["refs"]) <= set(by_id(rec))
    rule = rec["chain"][3]
    assert (rule["rule_id"], rule["level"]) == (d["rule_id"], d["level"])
    assert rec["chain"][-1]["level"] == d["level"]
    assert validate(rec) == []


def test_fired_rule_cites_the_evidence_that_triggered_it(cfg, run):
    rec = session(cfg, {"resp_rate": 26}, {"fainting": "yes"})
    d = run(rec)
    ids = by_id(rec)
    assert [ids[r]["item"] for r in d["refs"]] == ["fainting"]
    r05 = [m for m in d["also_matched"] if m["rule_id"] == "R05_vital_far_out"][0]
    assert [ids[r]["name"] for r in r05["refs"]] == ["resp_rate"]


def test_interpretation_statuses(cfg, run):
    rec = build(cfg, {"heart_rate": {"repeat": [102, 102], "margin": 3}, "resp_rate": {"repeat": [26, 27]},
                      "temperature": {"repeat": [36.6, 36.6], "quality": 0.3}})
    run(rec)
    interp = {i["name"]: i for i in rec["chain"][1]["items"]}
    assert interp["heart_rate"]["status"] == "borderline" and interp["heart_rate"]["confirmed"] is False
    assert interp["resp_rate"]["status"] == "out" and interp["resp_rate"]["beyond_urgent"] is True
    assert interp["temperature"]["status"] == "not_usable"


def test_context_explains_flagged_reading(cfg, run):
    rec = session(cfg, {"heart_rate": 108}, {"caffeine_last_2h": "yes"})
    run(rec)
    hr = next(m["id"] for m in rec["measurements"] if m["name"] == "heart_rate")
    caf = next(c for c in rec["chain"][2]["items"] if c["item"] == "caffeine_last_2h")
    assert caf["could_explain"] == [hr]
    expl = [u for u in rec["chain"][4]["items"] if u["kind"] == "possible_explanation"]
    assert expl and hr in expl[0]["refs"]
    assert rec["decision"]["level"] == "SEE_DOCTOR_SOON"              # context explains, it does not downgrade


def test_athlete_adjustment_is_shown(cfg, run):
    rec = session(cfg, {"heart_rate": {"repeat": [50, 50], "margin": 3}}, {"athlete": "yes"})
    run(rec)
    hr = next(i for i in rec["chain"][1]["items"] if i["name"] == "heart_rate")
    assert hr["normal"] == [50, 100] and "range_adjusted" in hr


def test_draft_status_and_placeholder_margins_are_disclosed(cfg, run):
    rec = session(cfg)
    run(rec)
    kinds = {u["kind"] for u in rec["chain"][4]["items"]}
    assert {"rules_draft", "margins_placeholder", "not_measured"} <= kinds   # BP/SpO2 not measured by the kiosk


def test_contacts_marked_unverified(cfg, run):
    rec = session(cfg, answers={"chest_pain": "yes"})
    run(rec)
    adv = rec["chain"][-1]
    assert adv["contacts"] and adv["contacts_verified"] is False


def test_fixed_wording_never_says_no_doctor_needed(cfg):
    texts = list(cfg["rules"]["advice"].values()) + list(cfg["rules"]["wording"].values()) \
        + [r["reason"] for r in cfg["rules"]["rules"]]
    for t in texts:
        low = t.lower().replace("’", "'")
        assert not any(p in low for p in ("don't need a doctor", "do not need a doctor", "no need to see",
                                          "diagnos")), t


def test_schema_rejects_bad_records(cfg):
    rec = session(cfg)
    rec["answers"][0]["answer"] = True
    rec["measurements"][0]["quality"] = 1.5
    rec["scores"].append(dict(rec["scores"][0]))                          # duplicate S1
    errs = validate(rec)
    assert any("answer" in e for e in errs) and any("quality" in e for e in errs)
    assert any("duplicate id S1" in e for e in errs)


def test_add_answer_rejects_booleans(cfg):
    with pytest.raises(TypeError):
        add_answer(build(cfg), "chest_pain", False)
