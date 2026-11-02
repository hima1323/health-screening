"""ED visits -> kiosk-like evidence records, the benchmark arms, and the SYS decision (brief P5).

Each dataset loader (mimic_ed.py, yale.py) returns a standard case table, one row per visit:
    case_id, patient_id, hr, rr, temp_c, spo2, sbp, dbp, o2_device, complaint, red_flags, esi, admitted, age, sex
`red_flags` lists the red_flags.yaml items (incl. self_harm) the chief complaint maps to. Context answers and
PHQ-2/GAD-2 do not exist in ED data, so those rules are inactive here.

Readings: an ED triage record has one set of vitals. `noise=None` gives two identical readings (the repeat agrees);
`noise="kiosk"` draws each reading as value + N(0, (margin / 1.96)^2), i.e. a device whose 95% error is the margin in
vital_ranges.yaml (placeholders until P6). A REMEASURE draws two fresh readings and decides again with `remeasured`.
"""
import copy
import re

import numpy as np

from triage.evidence import add_answer, add_measurement, new_record
from triage.rules_engine import decide, margin_for

KIOSK = [("heart_rate", "hr", "bpm", "rppg"), ("resp_rate", "rr", "/min", "thermal_nostril"),
         ("temperature", "temp_c", "C", "thermal_canthus")]
DEVICES = [("spo2", "spo2", "%", "device"), ("sbp", "sbp", "mmHg", "device"), ("dbp", "dbp", "mmHg", "device")]
ARMS = {"a_kiosk_vitals_red_flags": (KIOSK, True), "b_with_devices": (KIOSK + DEVICES, True),
        "c_vitals_only": (KIOSK, False), "d_red_flags_only": ([], True)}
REF_NAMES = {3: "URGENT", 2: "SEE_DOCTOR", 1: "SELF_CARE_COMPATIBLE"}


def reference(esi, admitted):
    """3 = ESI 1-2; 2 = ESI 3, or ESI 4-5 admitted; 1 = ESI 4-5 discharged; NaN = no ESI."""
    if esi is None or np.isnan(esi):
        return np.nan
    return 3 if esi <= 2 else 2 if esi == 3 or admitted else 1


def mimic_dev_mask(cases, frac=0.2, seed=0):
    """Starter kit E1.2 / E7: MIMIC-IV-ED rule derivation uses a random `frac` of SUBJECTS (dev); the benchmark
    tests on the rest only. The same seed everywhere, so the two never overlap. (The full release can restrict dev to
    the earlier anchor_year_group; the Demo has no year information.)"""
    subjects = np.sort(cases["patient_id"].unique())
    dev = set(np.random.default_rng(seed).choice(subjects, int(round(frac * len(subjects))), replace=False))
    return cases["patient_id"].isin(dev).to_numpy()


def complaint_patterns(cfg):
    return {k: re.compile(v["complaint_regex"], re.I) for k, v in cfg["red_flags"]["items"].items()}


def map_complaint(text, patterns):
    text = text if isinstance(text, str) else ""
    return [k for k, p in patterns.items() if p.search(text)]


def arm_config(cfg, arm):
    """Arm d has no sensors, so nothing is required for a decision."""
    if ARMS[arm][0]:
        return cfg
    c = copy.deepcopy(cfg)
    c["ranges"]["required"] = []
    return c


def _readings(value, margin, rng, noise):
    if noise is None:
        return [value, value]
    return [float(np.round(value + rng.normal(0, margin / 1.96), 1)) for _ in range(2)]


def build_record(case, arm, cfg, rng=None, noise=None):
    vitals, with_flags = ARMS[arm]
    rec = new_record(str(case["case_id"]), cfg, code="bench")
    for name, col, unit, source in vitals:
        v = case.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue                                   # not measured in the ED: the measure is simply absent
        margin = margin_for({"name": name, "source": source}, cfg)
        reps = _readings(float(v), margin, rng, noise)
        add_measurement(rec, name, float(np.mean(reps)), unit, 0.9, source, None, reps)
    if with_flags:
        flags = set(case["red_flags"])
        for item in cfg["red_flags"]["urgent_items"] + ["self_harm"]:
            add_answer(rec, item, "yes" if item in flags else "no")
    return rec


def remeasure(rec, case, cfg, rng, noise):
    rec = copy.deepcopy(rec)
    cols = {name: col for name, col, _, _ in KIOSK + DEVICES}
    for m in rec["measurements"]:
        reps = _readings(float(case[cols[m["name"]]]), margin_for(m, cfg), rng, noise)
        m["repeat_values"], m["value"], m["n_readings"] = reps, float(np.mean(reps)), len(reps)
    rec["flags"].append("remeasured")
    return rec


def sys_decision(case, arm, cfg, rng=None, noise=None):
    """Final SYS level for one case (one REMEASURE round allowed), plus the rule id and whether it re-measured."""
    rec = build_record(case, arm, cfg, rng, noise)
    d = decide(rec, cfg)
    remeasured = d["level"] == "REMEASURE"
    if remeasured:
        d = decide(remeasure(rec, case, cfg, rng, noise), cfg)
    return d["level"], d["rule_id"], remeasured


def all_kiosk_vitals_normal(case, cfg):
    """True when every available kiosk vital lies inside its normal range (no red flag or sensor could flag it)."""
    vals = [(name, case.get(col)) for name, col, _, _ in KIOSK]
    vals = [(n, v) for n, v in vals if v is not None and not np.isnan(v)]
    rng = cfg["ranges"]["measures"]
    return bool(vals) and all(rng[n]["normal"][0] <= v <= rng[n]["normal"][1] for n, v in vals)
