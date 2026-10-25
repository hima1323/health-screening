"""Picks the sample captures the demo station sends to the model, and copies the fold models they need.

A sample is one 2-minute n-back block of one ADABase subject (its 30 s windows, z-scored against that subject's own
baseline), paired with the fold model trained on the other 29 subjects, so the model never saw the person it reads.
fusion.py's own out-of-fold probabilities are stored with each sample; `serve.py --check` must reproduce them.

Run from the repo root with the reasoning model's environment (needs its data/features and results/):
    reasoning_model/.venv/bin/python model_service/export_samples.py
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RM = HERE.parent / "reasoning_model"
sys.path.insert(0, str(RM / "src"))
from features import FEAT, MODALITIES, zscore  # noqa: E402
import joblib  # noqa: E402

KEY = ["study", "phase", "level", "win_start"]
# n-back test levels: 1-3 = 1/2/3-back single task, 4-6 = dual task; binary label low = 1-back
TASKS = {1: "1-back task", 3: "3-back task", 4: "1-back dual task", 6: "3-back dual task"}
PICK = [("low", 1), ("high", 3), ("high", 6)]


def blocks():
    oof = pd.read_parquet(RM / "results" / "oof_fusion.parquet")
    oof = oof[(oof.study == "n-back") & (oof.phase == "test")]
    g = oof.groupby(["subject", "level"]).agg(prob=("prob", "mean"), n=("prob", "size")).reset_index()
    return oof, g


def full_sensors(sid):
    f = pd.read_parquet(FEAT / f"{sid}.parquet")
    return all(f.get(f"q_{m}", pd.Series([0])).fillna(0).ge(0.5).mean() > 0.9 for m in MODALITIES)


def main():
    oof, g = blocks()
    out_models, out_samples = HERE / "models", HERE / "samples"
    for d in (out_models, out_samples):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()

    used = set()
    for expect, level in PICK:
        rows = g[(g.level == level) & ((g.prob < 0.25) if expect == "low" else (g.prob > 0.8))]
        rows = rows[rows.subject.map(full_sensors)]
        # clearest block first, a person not used yet before one who is
        rows = rows.assign(seen=rows.subject.isin(used)).sort_values(["seen", "prob"], ascending=[True, expect == "low"])
        sid = rows.subject.iloc[0]
        used.add(sid)

        b = joblib.load(RM / "results" / "models" / "fusion" / f"{sid}.joblib")
        feat = zscore(pd.read_parquet(FEAT / f"{sid}.parquet"), b["ref"] or "stimulus").drop_duplicates(KEY)
        block = oof[(oof.subject == sid) & (oof.level == level)].sort_values("win_start")
        win = block[KEY].merge(feat, on=KEY, how="left")
        cols = [c for c in win.columns if c.startswith("q_") or c.endswith("_z") or c[:-2] + "_z" in win.columns
                or f"{c}_z" in win.columns]
        windows = [{c: (None if pd.isna(v) else float(v)) for c, v in r.items()} for r in win[cols].to_dict("records")]

        key = f"adabase-{sid[:4]}-{TASKS[level].split()[0]}{'-dual' if level > 3 else ''}"
        sample = {"key": key, "subject": sid, "dataset": "ADABase (Oppelt et al., Sensors 2023)",
                  "task": TASKS[level], "truth": expect, "expect": expect, "windowSeconds": 30,
                  "durationSeconds": int(block.win_start.max() + 30), "sensors": list(MODALITIES),
                  "fusion_py_probability_high": [round(float(p), 6) for p in block.prob], "windows": windows}
        (out_samples / f"{key}.json").write_text(json.dumps(sample))
        shutil.copy(RM / "results" / "models" / "fusion" / f"{sid}.joblib", out_models / f"{sid}.joblib")
        print(f"{key}: {len(windows)} windows, mean P(high) {block.prob.mean():.3f}")


if __name__ == "__main__":
    main()
