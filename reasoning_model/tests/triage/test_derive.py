"""Tests for the vignette benchmark (E6) and the rule-derivation tools (E1) on small synthetic inputs."""
import numpy as np
import pandas as pd
import pytest

from triage.bench import ed_cases
from triage.bench.vignettes import inter_rater_kappa, load_vignettes, metrics, normalise, run, sys_level, variants
from triage.derive import delphi, source_check
from triage.derive.mimic_dev_bands import band_table, wilson
from triage.evidence import ROOT


def vig(id_, label=None, **kw):
    v = {"id": id_, "age": 40, "measurements": {"heart_rate": [72, 73], "resp_rate": 15, "temperature": 36.6},
         "answers": {"chest_pain": False}, "clinician_labels": {"rater1": label, "rater2": label, "consensus": label}}
    v.update(kw)
    return normalise(v)


def test_normalise_turns_booleans_into_yes_no():
    v = vig("A", answers={"chest_pain": True, "athlete": False},
            measurements={"systolic_bp": 120, "heart_rate": [70, 71]})
    assert v["answers"] == {"chest_pain": "yes", "athlete": "no"} and "sbp" in v["measurements"]


def test_draft_vignettes_load():
    vs = load_vignettes()
    assert len(vs) >= 20 and all(v["clinician_labels"].get("consensus") is None for v in vs)


def test_sys_on_vignettes(cfg):
    assert sys_level(vig("A"), cfg)[:2] == ("SELF_CARE", "R99_default")
    v = vig("B", answers={"exercise_last_30min": "yes"}, measurements={"heart_rate": [106, 104]},
            measurements_after_rest={"heart_rate": [78, 79]})
    assert sys_level(v, cfg) == ("SELF_CARE", "R99_default", True)
    still = vig("C", answers={"exercise_last_30min": "yes"}, measurements={"heart_rate": [112, 110]})
    assert sys_level(still, cfg)[:2] == ("SEE_DOCTOR_SOON", "R06_vital_out")       # same readings after rest


def test_metrics_and_baselines(cfg):
    vs = [vig("U1", "URGENT", answers={"chest_pain": "yes"}), vig("U2", "URGENT", measurements={"heart_rate": [150, 150]}),
          vig("S1", "SEE_DOCTOR_SOON", measurements={"heart_rate": [112, 114]}), vig("C1", "SELF_CARE")]
    df = run(vs, cfg)
    m = metrics(df["SYS"], df["label"])
    assert m["urgent_sensitivity"][0] == 1.0 and m["exact_agreement"] == 1.0 and m["under_triage"] == 0
    assert metrics(df["D1_vitals_only"], df["label"])["urgent_sensitivity"][0] == 0.5     # misses the red flag
    assert metrics(df["D0_always_refer"], df["label"])["urgent_sensitivity"][0] == 0.0
    assert inter_rater_kappa(vs) == pytest.approx(1.0)


def test_variants_sit_on_the_thresholds(cfg):
    var = variants(vig("A"), cfg)
    hr = [w for w in var if "heart_rate_normal_high" in w["id"]]
    assert sorted(w["measurements"]["heart_rate"][0] for w in hr) == [95, 105]          # 100 -+ placeholder margin 5


def test_mimic_dev_split_is_by_subject_and_stable():
    cases = pd.DataFrame({"patient_id": np.repeat(np.arange(50), 3)})
    m1, m2 = ed_cases.mimic_dev_mask(cases), ed_cases.mimic_dev_mask(cases)
    assert (m1 == m2).all() and cases[m1]["patient_id"].nunique() == 10
    assert not set(cases[m1]["patient_id"]) & set(cases[~m1]["patient_id"])


def test_wilson_and_bands():
    p, lo, hi = wilson(5, 10)
    assert p == 0.5 and 0.2 < lo < 0.25 and 0.75 < hi < 0.8
    t = band_table(pd.DataFrame({"hr": [61, 63, 66, 70], "urgent": [True, False, True, True]}), "hr", 5)
    assert t["n"].tolist() == [2, 1, 1] and t["urgent_rate"].tolist() == [0.5, 1.0, 1.0]


def test_source_check_keeps_filled_rows(cfg, tmp_path):
    p = tmp_path / "sc.csv"
    t = source_check.build(cfg, p)
    assert any(r["item"] == "heart_rate.normal.high" for r in t)
    txt = p.read_text(encoding="utf-8").replace("heart_rate.normal.high,threshold,100,",
                                                "heart_rate.normal.high,threshold,100,", 1)
    import csv
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    for r in rows:
        if r["item"] == "heart_rate.normal.high":
            r["exact_source_value"] = "90"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, source_check.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    t = source_check.build(cfg, p)
    row = next(r for r in t if r["item"] == "heart_rate.normal.high")
    assert row["match"] == "MISMATCH" and row["exact_source_value"] == "90"


def test_delphi_scoring(tmp_path):
    for i, votes in enumerate([("agree", "agree"), ("agree", "modify"), ("agree", "agree"), ("agree", "agree"),
                               ("agree", "remove")]):
        pd.DataFrame({"rule_id": ["R01", "R05"], "rating(agree/modify/remove)": votes}).to_excel(
            tmp_path / f"r{i}.xlsx", sheet_name="rules", index=False)
    s = delphi.score(sorted(tmp_path.glob("*.xlsx"))).set_index("rule_id")
    assert s.loc["R01", "decision"] == "keep" and s.loc["R05", "agree_share"] == 0.6
    assert s.loc["R05", "decision"] != "keep"
