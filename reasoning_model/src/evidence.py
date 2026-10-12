"""Per-window evidence record (JSON lines) from the LOSO predictions -> results/evidence/<subject>.jsonl.

Each record: predictor label + calibrated probability, top-6 SHAP features (raw value, baseline z-score,
SHAP, learned direction under high load from the training folds, literature direction), quality indices.
Every number the reasoner may cite is in this record; nothing else is allowed.

    python src/evidence.py --subject 0
    python src/evidence.py --all
"""
import argparse
import json

import joblib
import numpy as np
import pandas as pd

from features import FEAT, MODALITIES, zscore
from load_adabase import subject_id
from train import RES

TOP = 6
# name -> (description, unit, expected direction under high cognitive load in the literature: +1, -1, None = mixed)
FEATURES = {
    "ecg_hr": ("heart rate", "bpm", +1), "ecg_rmssd": ("RMSSD heart-rate variability", "ms", -1),
    "ecg_sdnn": ("SDNN heart-rate variability", "ms", -1), "ecg_pnn50": ("pNN50 heart-rate variability", "%", -1),
    "ppg_rate": ("pulse rate", "bpm", +1), "ppg_amp": ("pulse amplitude", "a.u.", -1),
    "ppg_ptt": ("pulse transit time", "ms", -1), "eda_tonic": ("tonic skin conductance", "uS", +1),
    "eda_scr_count": ("skin conductance responses per window", "count", +1),
    "eda_scr_amp": ("skin conductance response amplitude", "uS", +1), "rsp_rate": ("breathing rate", "/min", +1),
    "rsp_depth": ("breathing depth", "a.u.", -1), "rsp_var": ("breathing irregularity", "CV", None),
    "emg_rms": ("trapezius muscle activity", "a.u.", +1), "skt_mean": ("finger skin temperature", "F", -1),
    "skt_slope": ("finger skin temperature slope", "F/s", -1), "eye_pupil_mean": ("pupil diameter", "mm", +1),
    "eye_pupil_slope": ("pupil diameter slope", "mm/s", None), "eye_blink_rate": ("blink rate", "/min", None),
    "eye_fix_dur": ("mean fixation duration", "s", None),
    **{f"au_{n}": (f"facial action unit {n} activation rate", "share", +1 if n == "04" else None)
       for n in ["01", "02", "04", "05", "06", "07", "09", "10", "11", "12", "14", "15", "17", "20", "23", "24",
                 "25", "26", "28", "43"]},
}


def num(x):
    return None if x is None or not np.isfinite(x) else float(f"{x:.4g}")


def build(sid):
    oof = pd.read_parquet(RES / "oof_binary.parquet")
    oof = oof[oof.subject == sid]
    bundle = joblib.load(RES / "models" / "binary" / f"{sid}.joblib")
    rules = bundle["rules"]
    feat = zscore(pd.read_parquet(FEAT / f"{sid}.parquet"), bundle["ref"] or "stimulus") \
        .set_index(["study", "phase", "level", "win_start"])
    shap_cols = [c for c in oof.columns if c.startswith("shap_")]
    recs = []
    for r in oof.itertuples(index=False):
        f = feat.loc[(r.study, r.phase, r.level, r.win_start)]
        label = "high" if r.prob >= 0.5 else "low"
        sv = pd.Series([getattr(r, c) for c in shap_cols], index=[c[5:] for c in shap_cols])  # keys end with _z
        # only features the model actually saw: measured and passing the same quality gate as train.load
        sv = sv[[np.isfinite(f.get(k, np.nan)) and f.get(f"q_{k.split('_')[0]}", 1) >= 0.5 for k in sv.index]]
        top = []
        for k in sv.abs().sort_values(ascending=False).index[:TOP]:
            name = k[:-2]
            desc, unit, lit = FEATURES[name]
            learned = rules.get(k, 0)
            top.append({"feature": name, "description": desc, "unit": unit, "value": num(f[name]),
                        "z": num(f[k]), "shap": num(sv[k]), "pushes_toward": "high" if sv[k] > 0 else "low",
                        "learned_direction_high_load": {1: "+", -1: "-", 0: "none"}[learned],
                        "literature_direction_high_load": {1: "+", -1: "-", None: "mixed"}[lit]})
        q = {m: num(f.get(f"q_{m}", np.nan)) for m in MODALITIES}
        recs.append({"subject": sid, "study": r.study, "phase": r.phase, "level": int(r.level),
                     "win_start": float(r.win_start), "label": label, "probability_high": num(r.prob),
                     "confidence": num(r.prob if label == "high" else 1 - r.prob), "top_features": top,
                     "quality": q, "low_quality_modalities": [m for m, v in q.items() if v is not None and v < 0.5]})
    out = RES / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{sid}.jsonl", "w") as fh:
        for x in recs:
            fh.write(json.dumps(x) + "\n")
    return recs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    sids = sorted(pd.read_parquet(RES / "oof_binary.parquet", columns=["subject"]).subject.unique()) if a.all \
        else [subject_id(a.subject)]
    for sid in sids:
        recs = build(sid)
        print(f"{sid}: {len(recs)} evidence records")
    if not a.all:
        print(json.dumps(recs[0], indent=1))
