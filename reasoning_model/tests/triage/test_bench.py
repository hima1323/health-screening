"""Benchmark building blocks: metrics, reference mapping, complaint mapping, arms, NEWS2, and the .RData reader."""
import gzip
import struct

import numpy as np
import pandas as pd
import pytest

from triage.bench import baselines as B
from triage.bench import ed_cases as E
from triage.bench import metrics as M
from triage.bench import rdata_stream


def test_clopper_pearson():
    p, lo, hi = M.clopper_pearson(60, 60)
    assert p == 1 and hi == 1 and 0.94 < lo < 0.95          # brief: 60/60 urgent vignettes -> lower bound ~0.95
    assert M.clopper_pearson(0, 10)[1] == 0


def test_weighted_kappa():
    assert M.weighted_kappa([1, 2, 3, 3], [1, 2, 3, 3]) == pytest.approx(1)
    assert M.weighted_kappa([1, 2, 3], [3, 2, 1]) < 0


def test_decision_table():
    lv = np.array(["URGENT", "SELF_CARE", "SEE_DOCTOR_SOON", "SELF_CARE", "RETAKE"], object)
    t = M.decision_table(lv, [3, 3, 2, 1, 1], [True, True, False, False, False])
    assert t["urgent_sensitivity"][0] == 0.5
    assert t["admitted_told_self_care"][0] == 0.5
    assert t["self_care_rate_low_acuity"][0] == 1.0
    assert t["retake_share"] == 0.2 and t["n_decided"] == 4
    assert t["confusion_ref_rows_sys_cols_U_S_C"] == [[1, 0, 1], [0, 1, 0], [0, 0, 1]]


def test_mcnemar_and_bootstrap():
    r = M.mcnemar([True, False, False], [True, True, True])
    assert (r["only_a_missed"], r["only_b_missed"]) == (0, 2)
    d, lo, hi = M.bootstrap_diff([1, 1, 1, 1], [0, 0, 0, 0], groups=[1, 1, 2, 2], n_boot=50)
    assert d == lo == hi == 1


@pytest.mark.parametrize("esi, admitted, ref", [(1, False, 3), (2, True, 3), (3, False, 2), (4, True, 2),
                                                (5, False, 1)])
def test_reference(esi, admitted, ref):
    assert E.reference(esi, admitted) == ref
    assert np.isnan(E.reference(np.nan, True))


def test_complaint_mapping(cfg):
    pats = E.complaint_patterns(cfg)
    assert E.map_complaint("CHEST PAIN, SOB", pats) == ["chest_pain", "severe_breathlessness"]
    assert E.map_complaint("Syncope", pats) == ["fainting"]
    assert E.map_complaint("S/P FALL", pats) == []
    assert E.map_complaint("SI", pats) == ["self_harm"]
    assert E.map_complaint(None, pats) == []


CASE = {"case_id": 1, "hr": 72.0, "rr": 16.0, "temp_c": 36.8, "spo2": 90.0, "sbp": 120.0, "dbp": 80.0,
        "red_flags": [], "o2_device": False}


def test_arms(cfg):
    assert E.sys_decision(CASE, "a_kiosk_vitals_red_flags", cfg)[0] == "SELF_CARE"
    assert E.sys_decision(CASE, "b_with_devices", cfg)[0] == "URGENT"          # SpO2 90 only seen with devices
    flagged = {**CASE, "red_flags": ["chest_pain"]}
    assert E.sys_decision(flagged, "a_kiosk_vitals_red_flags", cfg)[0] == "URGENT"
    assert E.sys_decision(flagged, "c_vitals_only", cfg)[0] == "SELF_CARE"     # arm c ignores red flags
    assert E.sys_decision(flagged, "d_red_flags_only", E.arm_config(cfg, "d_red_flags_only"))[0] == "URGENT"
    missing = {**CASE, "hr": np.nan}
    assert E.sys_decision(missing, "a_kiosk_vitals_red_flags", cfg)[0] == "RETAKE"


def test_kiosk_noise_is_seeded(cfg):
    case = {**CASE, "hr": 101.0}
    r1 = E.sys_decision(case, "a_kiosk_vitals_red_flags", cfg, np.random.default_rng(3), "kiosk")
    r2 = E.sys_decision(case, "a_kiosk_vitals_red_flags", cfg, np.random.default_rng(3), "kiosk")
    assert r1 == r2


@pytest.mark.parametrize("vitals, level", [
    ({}, "SELF_CARE"),                                    # all missing -> score 0
    ({"hr": 95}, "SEE_DOCTOR_SOON"),                      # 1 point
    ({"hr": 135}, "URGENT"),                              # single parameter scoring 3
    ({"rr": 22, "hr": 115, "temp_c": 38.5}, "URGENT"),    # 2 + 2 + 1 = 5
    ({"temp_c": 36.0}, "SEE_DOCTOR_SOON"),                # published band upper limits are inclusive (35.1-36.0: 1)
    ({"temp_c": 36.05}, "SELF_CARE"),                     # anything above 36.0 is in the next band
])
def test_news2(vitals, level):
    case = {"rr": np.nan, "spo2": np.nan, "sbp": np.nan, "hr": np.nan, "temp_c": np.nan, "red_flags": [],
            "o2_device": False, **vitals}
    assert B.d3_news2(pd.DataFrame([case]))[0] == level


def _rdata(path, cols):
    """Write a minimal XDR .RData holding data.frame `df` with numeric, integer, factor and character columns."""
    out = [b"RDX3\n", b"X\n", struct.pack(">iii", 3, 0x040000, 0x030500), struct.pack(">i", 5), b"UTF-8"]
    i = lambda *v: struct.pack(">" + "i" * len(v), *v)
    chars = lambda s: i(0x00040009, len(s)) + s.encode()
    sym = lambda s: i(1) + chars(s)
    strs = lambda xs: i(16, len(xs)) + b"".join(chars(x) for x in xs)
    body = i(2 | (1 << 10)) + sym("df") + i(19 | (1 << 9), len(cols))           # pairlist(df = list(...))
    for kind, vals in cols.values():
        if kind == "double":
            body += i(14, len(vals)) + struct.pack(f">{len(vals)}d", *vals)
        elif kind == "integer":
            body += i(13, len(vals)) + struct.pack(f">{len(vals)}i", *vals)
        elif kind == "character":
            body += strs(vals)
        else:                                                                    # factor: codes + levels attr
            codes, levels = vals
            body += i(13 | (1 << 9), len(codes)) + struct.pack(f">{len(codes)}i", *codes)
            body += i(2 | (1 << 10)) + sym("levels") + strs(levels) + i(254)
    body += i(2 | (1 << 10)) + sym("names") + strs(list(cols)) + i(254)       # attributes of the list
    body += i(254)                                                               # end of saved pairlist
    with gzip.open(path, "wb") as f:
        f.write(b"".join(out) + body)


def test_rdata_stream(tmp_path):
    p = tmp_path / "x.RData"
    na = -2 ** 31
    _rdata(p, {"hr": ("double", [70.0, float("nan"), 101.5]), "esi": ("factor", ([1, 3, na], ["1", "2", "3"])),
               "n": ("integer", [1, na, 3]), "cc": ("character", ["a", "b", "c"])})
    assert rdata_stream.columns(p) == [("hr", "double", False), ("esi", "integer", True), ("n", "integer", False),
                                       ("cc", "character", False)]
    df = rdata_stream.read(p, ["esi", "hr", "n"])
    assert list(df.columns) == ["hr", "esi", "n"]
    assert df["hr"].iloc[2] == 101.5 and np.isnan(df["hr"].iloc[1])
    assert list(df["esi"].astype(object)[:2]) == ["1", "3"] and pd.isna(df["esi"].iloc[2])
    assert df["n"].iloc[0] == 1 and np.isnan(df["n"].iloc[1])
