"""Yale ED triage data (Hong, Haimovich & Taylor, PLOS ONE 2018; Zenodo 1308993) -> standard case table (ed_cases.py).

560,486 adult ED visits (3 EDs, 2014-2017), triage vitals, ESI, top-200 chief complaints as one-hot `cc_*` columns,
disposition (Admit / Discharge). The 972-column R frame is streamed column-wise (rdata_stream.py) because it does not
fit the 8 GB RAM budget. There is no patient or date column, so the dev/test split is random by visit (stated in the
report); the brief's subject- and time-wise split is not possible on this data.

CC_RED_FLAGS mirrors the complaint regexes in configs/triage/red_flags.yaml for these fixed complaint names (DRAFT,
for clinician review). Breathlessness complaints are mapped to `severe_breathlessness` although the ED record does not
say how severe they were; that overstates the red flag (noted in the report).

    python -m triage.bench.yale --build        # -> data/public/yale_triage/cases.parquet   (from reasoning_model/src)
"""
import argparse

import numpy as np
import pandas as pd

from triage.bench import rdata_stream
from triage.evidence import ROOT

DIR = ROOT / "data" / "public" / "yale_triage"
RDATA = DIR / "yaleemmlc-admissionprediction-5cf50bc" / "Results" / "5v_cleandf.RData"
CASES = DIR / "cases.parquet"
CC_RED_FLAGS = {
    "chest_pain": ["cc_chestpain", "cc_chesttightness"],
    "severe_breathlessness": ["cc_shortnessofbreath", "cc_dyspnea", "cc_breathingdifficulty", "cc_breathingproblem",
                              "cc_respiratorydistress"],
    "fainting": ["cc_syncope", "cc_nearsyncope", "cc_lossofconsciousness"],
    "confusion": ["cc_alteredmentalstatus", "cc_confusion", "cc_lethargy", "cc_unresponsive"],
    "stroke_signs": ["cc_strokealert", "cc_numbness", "cc_extremityweakness", "cc_weakness"],
    "worst_headache": [],                       # no "worst / thunderclap headache" complaint in the top 200
    "severe_bleeding": ["cc_gibleeding"],       # starter kit regex "gi bleed"; severity not recorded (overstates)
    "severe_allergy": ["cc_allergicreaction"],  # starter kit regex "allergic reaction"; severity not recorded
    "self_harm": ["cc_suicidal", "cc_overdose-intentional"],
}
BASE = ["esi", "age", "gender", "disposition", "dep_name", "triage_vital_hr", "triage_vital_rr", "triage_vital_temp",
        "triage_vital_o2", "triage_vital_o2_device", "triage_vital_sbp", "triage_vital_dbp"]


def build(batch=40):
    names = [n for n, _, _ in rdata_stream.columns(RDATA)]
    cc = [n for n in names if n.startswith("cc_")]
    base = rdata_stream.read(RDATA, BASE)
    flags = pd.DataFrame(index=base.index)
    for i in range(0, len(cc), batch):                    # one pass per batch keeps peak RAM low
        part = rdata_stream.read(RDATA, cc[i:i + batch])
        flags = pd.concat([flags, (part.fillna(0) > 0).astype("int8")], axis=1)
        print(f"complaint columns {min(i + batch, len(cc))}/{len(cc)}", flush=True)
    complaint = flags.apply(lambda r: "; ".join(c[3:].replace("-", " ") for c in r.index[r.values == 1]), axis=1)
    red = pd.DataFrame({k: flags[v].max(axis=1) if v else 0 for k, v in CC_RED_FLAGS.items()})
    temp_f = base["triage_vital_temp"]
    out = pd.DataFrame({
        "case_id": np.arange(len(base)), "patient_id": np.arange(len(base)),
        "hr": base["triage_vital_hr"], "rr": base["triage_vital_rr"],
        "temp_c": np.where(temp_f > 50, (temp_f - 32) * 5 / 9, temp_f),     # degrees F in this data
        "spo2": base["triage_vital_o2"], "sbp": base["triage_vital_sbp"], "dbp": base["triage_vital_dbp"],
        "o2_device": base["triage_vital_o2_device"].fillna(0) > 0,
        "complaint": complaint.values,
        "red_flags": red.apply(lambda r: ",".join(r.index[r.values == 1]), axis=1).values,
        "esi": pd.to_numeric(base["esi"].astype(str), errors="coerce"),
        "admitted": base["disposition"].astype(str).eq("Admit"),
        "age": base["age"], "sex": base["gender"].astype(str), "site": base["dep_name"].astype(str),
    })
    out.to_parquet(CASES, index=False)
    return out


def load():
    """The red flags are recomputed from the stored complaint names with CC_RED_FLAGS, so the cache follows any change
    of the red-flag list without re-streaming the RData file."""
    df = pd.read_parquet(CASES)
    names = {cc[3:].replace("-", " "): flag for flag, ccs in CC_RED_FLAGS.items() for cc in ccs}
    df["red_flags"] = df["complaint"].map(
        lambda s: sorted({names[c] for c in s.split("; ") if c in names}))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    df = build() if ap.parse_args().build else load()
    df["red_flags"] = df["red_flags"].map(lambda s: s if isinstance(s, list) else [x for x in s.split(",") if x])
    print(f"{len(df)} visits; ESI {df.esi.value_counts(dropna=False).sort_index().to_dict()}; "
          f"admitted {df.admitted.mean():.1%}")
    print(df[["hr", "rr", "temp_c", "spo2", "sbp", "dbp"]].describe().round(1).to_string())
    print(f"missing HR {df.hr.isna().mean():.1%}; complaint mapped to a red flag {df.red_flags.map(bool).mean():.1%}; "
          f"no complaint {df.complaint.eq('').mean():.1%}")
