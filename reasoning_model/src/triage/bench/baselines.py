"""Baselines for the decision benchmarks (brief §5.1). D1 (vitals-only) and D2 (red-flags-only) are SYS on arms c and
d (ed_cases.ARMS), so they are not repeated here.

D0  always refer: SEE_DOCTOR_SOON for everyone.
D3  NEWS2 aggregate score (Royal College of Physicians 2017), a hospital-validated reference, NOT kiosk-validated.
    Missing parameters score 0; consciousness is scored 3 only when the complaint maps to `confusion`.
    Kiosk mapping (our choice): total >= 5 or any single parameter scoring 3 -> URGENT; 1-4 -> SEE_DOCTOR_SOON;
    0 -> SELF_CARE.
D4  LLM alone: the local Ollama model gets the same case text and picks the level (no rules). Local only.
D5  shallow decision tree (depth <= 3), fitted on the dev split: shows which thresholds the data suggests, for the
    clinician; never deployed.
ML  LightGBM on the same inputs as D5, fitted on the dev split: an upper reference for what these inputs allow;
    never deployed (the decision must stay with the reviewed rules).
"""
import json
import time
import urllib.request

import numpy as np
import pandas as pd

LEVELS3 = {3: "URGENT", 2: "SEE_DOCTOR_SOON", 1: "SELF_CARE"}


def d0_always_refer(cases):
    return np.array(["SEE_DOCTOR_SOON"] * len(cases), object)


def _band(v, bands):
    """bands: [(upper_inclusive, score), ...] in ascending order; the last upper is inf."""
    if v is None or np.isnan(v):
        return 0
    for upper, score in bands:
        if v <= upper:
            return score
    return 0


NEWS2 = {
    "rr": [(8, 3), (11, 1), (20, 0), (24, 2), (np.inf, 3)],
    "spo2": [(91, 3), (93, 2), (95, 1), (np.inf, 0)],
    "sbp": [(90, 3), (100, 2), (110, 1), (219, 0), (np.inf, 3)],
    "hr": [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2), (np.inf, 3)],
    "temp_c": [(35.0, 3), (36.0, 1), (38.0, 0), (39.0, 1), (np.inf, 2)],
}


def news2_scores(case, use=("rr", "spo2", "sbp", "hr", "temp_c")):
    s = {k: _band(case.get(k), NEWS2[k]) for k in use}
    if "spo2" in use and case.get("o2_device") is True:
        s["o2"] = 2
    s["consciousness"] = 3 if "confusion" in case["red_flags"] else 0
    return s


def d3_news2(cases, use=("rr", "spo2", "sbp", "hr", "temp_c")):
    out = []
    for case in cases.to_dict("records"):
        s = news2_scores(case, use)
        total = sum(s.values())
        out.append("URGENT" if total >= 5 or max(s.values()) == 3 else "SEE_DOCTOR_SOON" if total else "SELF_CARE")
    return np.array(out, object)


# ---------------------------------------------------------------- D4: local LLM alone

D4_SYSTEM = """You are helping a self-service health kiosk decide what a person should do next.
Choose exactly one level:
URGENT = needs medical help now; SEE_DOCTOR_SOON = should see a doctor in the next few days;
SELF_CARE = no warning signs, look after yourself.
Reply with JSON only: {"level": "URGENT" | "SEE_DOCTOR_SOON" | "SELF_CARE"}"""


def case_text(case, vitals=("hr", "rr", "temp_c", "spo2", "sbp", "dbp")):
    names = {"hr": ("heart rate", "bpm"), "rr": ("breathing rate", "/min"), "temp_c": ("temperature", "C"),
             "spo2": ("oxygen saturation", "%"), "sbp": ("systolic blood pressure", "mmHg"),
             "dbp": ("diastolic blood pressure", "mmHg")}
    parts = []
    for k in vitals:
        v = case.get(k)
        if v is not None and not np.isnan(v):
            parts.append(f"{names[k][0]} {v:.1f} {names[k][1]}" if k == "temp_c" else f"{names[k][0]} {v:.0f} {names[k][1]}")
    complaint = case.get("complaint") or "not given"
    return f"Main complaint: {complaint}. Measurements: {', '.join(parts) or 'none'}."


def d4_llm(cases, model="qwen2.5:3b-instruct", url="http://localhost:11434/api/chat",
           vitals=("hr", "rr", "temp_c", "spo2", "sbp", "dbp")):
    """Returns (levels, latencies_s). Unparseable output -> 'INVALID'."""
    schema = {"type": "object", "required": ["level"],
              "properties": {"level": {"type": "string", "enum": ["URGENT", "SEE_DOCTOR_SOON", "SELF_CARE"]}}}
    levels, lat = [], []
    for case in cases.to_dict("records"):
        body = {"model": model, "stream": False, "format": schema, "options": {"temperature": 0, "seed": 0},
                "keep_alive": "30m",
                "messages": [{"role": "system", "content": D4_SYSTEM},
                             {"role": "user", "content": case_text(case, vitals)}]}
        t = time.perf_counter()
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            try:
                lv = json.loads(json.loads(r.read())["message"]["content"])["level"]
            except (ValueError, KeyError, TypeError):
                lv = "INVALID"
        lat.append(time.perf_counter() - t)
        levels.append(lv if lv in ("URGENT", "SEE_DOCTOR_SOON", "SELF_CARE") else "INVALID")
    return np.array(levels, object), np.array(lat)


# ---------------------------------------------------------------- D5 tree and the LightGBM reference (trained)

def features(cases, red_flag_items, vitals=("hr", "rr", "temp_c")):
    X = pd.DataFrame({v: cases[v].astype(float) for v in vitals})
    for item in red_flag_items:
        X[f"rf_{item}"] = cases["red_flags"].map(lambda f, i=item: int(i in f))
    return X


def fit_tree(X, y, seed=0):
    from sklearn.tree import DecisionTreeClassifier
    return DecisionTreeClassifier(max_depth=3, class_weight="balanced", min_samples_leaf=200,
                                  random_state=seed).fit(X, y)


def fit_lgbm(X, y, seed=0, n_jobs=6):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, class_weight="balanced",
                              random_state=seed, n_jobs=n_jobs, verbose=-1).fit(X, y)


def predict_levels(model, X):
    return np.array([LEVELS3[int(c)] for c in model.predict(X)], object)


def tree_rules(tree, names):
    from sklearn.tree import export_text
    return export_text(tree, feature_names=list(names), class_names=[LEVELS3[int(c)] for c in tree.classes_])
