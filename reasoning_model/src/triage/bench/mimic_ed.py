"""MIMIC-IV-ED -> standard case table (see ed_cases.py). Works on the open Demo (data/public/mimic_iv_ed_demo) and,
once the data use agreement is signed, on the full release under data/restricted/mimic_iv_ed (never sent to any
external service; results files hold aggregates only).

triage.temperature is in degrees F (converted); acuity = ESI; admitted = edstays.disposition == ADMITTED.

    python -m triage.bench.mimic_ed [--root <folder with ed/*.csv.gz>]      (from reasoning_model/src)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from triage.bench.ed_cases import complaint_patterns, map_complaint
from triage.evidence import ROOT
from triage.rules_engine import load_config

DEMO = ROOT / "data" / "public" / "mimic_iv_ed_demo" / "mimic-iv-ed-demo-2.2" / "ed"


def f_to_c(f):
    return (f - 32) * 5 / 9


def load(root=DEMO, cfg=None):
    cfg = cfg or load_config()
    root = Path(root)
    tri = pd.read_csv(root / "triage.csv.gz")
    stays = pd.read_csv(root / "edstays.csv.gz")
    df = tri.merge(stays[["stay_id", "gender", "disposition"]], on="stay_id", how="left")
    temp = pd.to_numeric(df["temperature"], errors="coerce")
    temp = temp.where((temp > 85) & (temp < 110))            # implausible degrees-F entries -> missing
    pats = complaint_patterns(cfg)
    num = lambda c, lo, hi: pd.to_numeric(df[c], errors="coerce").where(lambda s: (s >= lo) & (s <= hi))
    return pd.DataFrame({
        "case_id": df["stay_id"], "patient_id": df["subject_id"],
        "hr": num("heartrate", 20, 250), "rr": num("resprate", 4, 60), "temp_c": f_to_c(temp),
        "spo2": num("o2sat", 50, 100), "sbp": num("sbp", 40, 300), "dbp": num("dbp", 20, 200),
        "o2_device": np.nan, "complaint": df["chiefcomplaint"].fillna(""),
        "red_flags": [map_complaint(t, pats) for t in df["chiefcomplaint"].fillna("")],
        "esi": pd.to_numeric(df["acuity"], errors="coerce"), "admitted": df["disposition"].eq("ADMITTED"),
        "age": np.nan, "sex": df["gender"],
    })


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEMO))
    cases = load(ap.parse_args().root)
    print(f"{len(cases)} visits, {cases.patient_id.nunique()} patients; ESI {cases.esi.value_counts().sort_index().to_dict()}")
    print(f"complaint mapped to a red flag: {cases.red_flags.map(bool).mean():.1%}; "
          f"HR missing: {cases.hr.isna().mean():.1%}")
