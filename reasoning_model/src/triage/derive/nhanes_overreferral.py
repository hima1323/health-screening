"""E1.3 healthy-population over-referral: the survey-weighted share of ordinary adults (NHANES, 18-65) whose resting
pulse or blood pressure is outside each draft cut-off, by age group and sex. It estimates how many everyday kiosk
users each rule would flag, to set next to the MIMIC sensitivity (sensitivity vs over-referral table).

NHANES 2017-2018 examination files (open, CDC): DEMO_J (age RIDAGEYR, sex RIAGENDR, MEC weight WTMEC2YR) and BPX_J
(60-s pulse BPXPLS, systolic BPXSY1-3, diastolic BPXDI1-3; the mean of the available readings is used). NHANES has
no breathing rate or temperature. Put the two .XPT files in data/public/nhanes/ (or run with --download, which
fetches them from the CDC site; ~3 MB).

    python -m triage.derive.nhanes_overreferral [--download]          (from reasoning_model/src)
"""
import argparse
import json
import urllib.request

import numpy as np
import pandas as pd

from triage.evidence import ROOT
from triage.rules_engine import load_config

DATA = ROOT / "data" / "public" / "nhanes"
OUT = ROOT / "results" / "triage" / "derive"
FILES = {"DEMO_J.XPT": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt",
         "BPX_J.XPT": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BPX_J.xpt"}
MEASURES = {"heart_rate": "pulse", "sbp": "sbp", "dbp": "dbp"}


def download():
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        if not (DATA / name).exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, DATA / name)


def load():
    missing = [n for n in FILES if not (DATA / n).exists()]
    if missing:
        raise SystemExit(f"missing {missing} in {DATA}: download them from the CDC NHANES 2017-2018 pages "
                         f"({', '.join(FILES.values())}) or run with --download")
    demo = pd.read_sas(DATA / "DEMO_J.XPT", format="xport")
    bpx = pd.read_sas(DATA / "BPX_J.XPT", format="xport")
    df = demo[["SEQN", "RIDAGEYR", "RIAGENDR", "WTMEC2YR"]].merge(bpx, on="SEQN")
    out = pd.DataFrame({"age": df["RIDAGEYR"], "sex": df["RIAGENDR"].map({1: "male", 2: "female"}),
                        "weight": df["WTMEC2YR"], "pulse": df["BPXPLS"],
                        "sbp": df[["BPXSY1", "BPXSY2", "BPXSY3"]].mean(axis=1),
                        "dbp": df[["BPXDI1", "BPXDI2", "BPXDI3"]].replace(0, np.nan).mean(axis=1)})
    return out[(out["age"] >= 18) & (out["age"] <= 65) & (out["weight"] > 0)]


def weighted_share(flag, w):
    ok = ~np.isnan(flag)
    return float(np.sum(w[ok] * flag[ok]) / np.sum(w[ok])) if ok.any() else float("nan")


def overreferral(df, cfg):
    rows = []
    df = df.assign(age_group=pd.cut(df["age"], [17, 40, 65], labels=["18-40", "41-65"]))
    groups = [("all", df)] + [(f"age {g}", x) for g, x in df.groupby("age_group", observed=True)] + \
             [(f"sex {g}", x) for g, x in df.groupby("sex")]
    for name, col in MEASURES.items():
        spec = cfg["ranges"]["measures"][name]
        for kind in ("normal", "urgent"):
            for side, v in zip(("low", "high"), spec[kind]):
                if v is None:
                    continue
                for gname, g in groups:
                    x = g[col].to_numpy(float)
                    flag = np.where(np.isnan(x), np.nan, (x < v) if side == "low" else (x > v))
                    rows.append({"measure": name, "cutoff": f"{kind} {side} ({'<' if side == 'low' else '>'} {v})",
                                 "group": gname, "n": int((~np.isnan(x)).sum()),
                                 "weighted_share_flagged": weighted_share(flag, g["weight"].to_numpy(float))})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch DEMO_J / BPX_J from the CDC site")
    a = ap.parse_args()
    if a.download:
        download()
    t = overreferral(load(), load_config())
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "nhanes_overreferral.csv", index=False)
    piv = t.pivot_table(index=["measure", "cutoff"], columns="group", values="weighted_share_flagged")
    print((piv * 100).round(1).to_string())
    (OUT / "nhanes_overreferral.json").write_text(json.dumps(t.to_dict("records"), indent=1), encoding="utf-8")
