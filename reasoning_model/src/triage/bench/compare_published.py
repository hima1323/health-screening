"""Put the triage prototype next to published benchmarks, using their metrics on our Yale split.

Published reference numbers (copied from the papers; not re-run):
  Hong, Haimovich & Taylor, PLOS ONE 2018 (same Yale data): admission AUC from triage information only
      (hospital, arrival time and mode, ESI, demographics, triage vitals, chief complaint) 0.87 for LR / XGBoost /
      DNN; with patient history 0.92 (XGBoost). Random 10% test set; outcome admit vs discharge.
  Xie et al., Sci Data 2022 (MIMIC-IV-ED benchmark, 441,437 visits, 20% test): hospitalization AUROC at triage
      GB 0.820, MLP 0.823, LR 0.809, ESI 0.711, NEWS 0.581, NEWS2 0.563; critical outcome (in-hospital death or ICU
      within 12 h) GB 0.881, ESI 0.804, NEWS2 0.616.
  Semigran et al., BMJ 2015 (23 online symptom checkers, 45 vignettes): appropriate triage 57% overall; 80% of
      emergent, 55% of non-emergent and 33% of self-care vignettes.

What is re-computed here on the Yale test split (same seed as run_bench.py; models fitted on the 20% dev split):
  admission AUROC (bootstrap 95% CI) for an Hong-style triage-only LightGBM (sanity check of our data loading),
  the same without ESI, kiosk-knowable inputs, ESI alone, NEWS2 alone, and the SYS level; SYS's operating point for
  admission; and the Semigran-style "correct level per reference class" from bench_results.json.

    python -m triage.bench.compare_published          (from reasoning_model/src; run after run_bench)
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from triage.bench import baselines as B
from triage.bench import ed_cases as E
from triage.bench import rdata_stream, yale
from triage.bench.run_bench import OUT, RF_ITEMS, prepare, run_sys
from triage.rules_engine import load_config

HONG_EXTRA = ["dep_name", "arrivalmode", "arrivalmonth", "arrivalday", "arrivalhour_bin", "ethnicity", "race", "lang",
              "religion", "maritalstatus", "employstatus", "insurance_status", "disposition", "esi", "gender", "age",
              "triage_vital_o2_device"]
PUBLISHED = {
    "Hong 2018, Yale, triage-only (LR / XGBoost / DNN)": "0.87 / 0.87 / 0.87",
    "Hong 2018, Yale, full incl. history (XGBoost)": "0.92",
    "Xie 2022, MIMIC-IV-ED, gradient boosting": "0.820",
    "Xie 2022, MIMIC-IV-ED, ESI alone": "0.711",
    "Xie 2022, MIMIC-IV-ED, NEWS2 alone": "0.563",
}


def auroc_ci(y, s, n_boot=200, seed=0):
    y, s = np.asarray(y), np.asarray(s, float)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        boots.append(roc_auc_score(y[i], s[i]))
    return float(roc_auc_score(y, s)), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main():
    cfg = load_config()
    cases = yale.load()
    extra = rdata_stream.read(yale.RDATA, HONG_EXTRA)        # same row order as cases.parquet
    cc_cols = [n for n, _, _ in rdata_stream.columns(yale.RDATA) if n.startswith("cc_")]
    cc = pd.concat([rdata_stream.read(yale.RDATA, cc_cols[i:i + 40]).fillna(0).astype("int8")
                    for i in range(0, len(cc_cols), 40)], axis=1)
    disp = extra["disposition"].astype(str)
    df = prepare(cases)                                       # drops visits without ESI, adds `ref`
    keep = df.index[disp.loc[df.index].isin(["Admit", "Discharge"])]
    rng = np.random.default_rng(0)
    is_dev = pd.Series(rng.random(len(df)) < 0.2, index=df.index)   # identical to run_bench.py
    df = df.loc[keep]
    is_dev = is_dev.loc[keep]
    y = df["admitted"].astype(int)

    cat = extra.loc[keep, [c for c in HONG_EXTRA if c not in ("disposition", "age", "esi", "triage_vital_o2_device")]]
    cat = cat.apply(lambda s: s.cat.codes if hasattr(s, "cat") else s).astype("int16")
    vit = df[["hr", "rr", "temp_c", "spo2", "sbp", "dbp"]].assign(o2_device=df["o2_device"].astype(int))
    esi = df[["esi"]]
    age = df[["age"]]
    cck = cc.loc[keep]
    sets = {
        "Hong-style triage-only (ESI + demographics + arrival + vitals + 200 complaints)":
            pd.concat([cat, esi, age, vit, cck], axis=1),
        "Same without ESI (no triage nurse)": pd.concat([cat, age, vit, cck], axis=1),
        "Kiosk-knowable: age, sex, HR, RR, temp, 200 complaints":
            pd.concat([age, cat[["gender"]], vit[["hr", "rr", "temp_c"]], cck], axis=1),
        "Kiosk prototype inputs: HR, RR, temp + 7 red flags": B.features(df, RF_ITEMS, ("hr", "rr", "temp_c")),
    }
    res = {"n_test": int((~is_dev).sum()), "n_dev": int(is_dev.sum()),
           "admission_rate_test": float(y[~is_dev].mean()), "auroc": {}}
    for name, X in sets.items():
        X = X.copy()
        X.columns = [str(c).replace(" ", "_") for c in X.columns]
        m = B.fit_lgbm(X[is_dev.values], y[is_dev.values].values)
        p = m.predict_proba(X[~is_dev.values])[:, 1]
        res["auroc"][f"LightGBM: {name}"] = auroc_ci(y[~is_dev.values], p)
        print(name, res["auroc"][f"LightGBM: {name}"], flush=True)
    t = df[~is_dev.values]
    res["auroc"]["ESI alone (lower = more urgent)"] = auroc_ci(y[~is_dev.values], -t["esi"])
    news = [sum(B.news2_scores(c).values()) for c in t.to_dict("records")]
    res["auroc"]["NEWS2 alone (all vitals, missing = 0)"] = auroc_ci(y[~is_dev.values], news)

    ts = t[t["hr"].notna()]
    ys = ts["admitted"].astype(int).values
    for arm in ("a_kiosk_vitals_red_flags", "b_with_devices"):
        lv = run_sys(ts, arm, cfg)[0]
        score = np.array([{"URGENT": 3, "SEE_DOCTOR_SOON": 2, "SELF_CARE": 1}.get(l, 2) for l in lv])
        res["auroc"][f"SYS {arm} level (3 / 2 / 1), visits with HR"] = auroc_ci(ys, score)
        refer = np.isin(lv, ["URGENT", "SEE_DOCTOR_SOON"])
        res[f"SYS_{arm}_refer_vs_admission"] = {
            "n": int(len(ys)), "sensitivity": float(refer[ys == 1].mean()),
            "specificity": float((~refer)[ys == 0].mean()), "ppv": float(ys[refer].mean()),
            "npv": float(1 - ys[~refer].mean())}
        print(arm, res[f"SYS_{arm}_refer_vs_admission"], flush=True)

    bench = json.loads((OUT / "bench_results.json").read_text())
    sem = {}
    for key in ("SYS_a_kiosk_vitals_red_flags", "SYS_b_with_devices", "D3_news2_devices", "ML_lgbm_kiosk"):
        cm = np.array(bench["yale_test"][key]["confusion_ref_rows_sys_cols_U_S_C"])
        sem[key] = {"urgent": cm[0, 0] / cm[0].sum(), "see_doctor": cm[1, 1] / cm[1].sum(),
                    "self_care": cm[2, 2] / cm[2].sum(), "overall": np.trace(cm) / cm.sum()}
    res["correct_level_per_reference_class"] = sem
    (OUT / "comparison_results.json").write_text(json.dumps(res, indent=1, default=float))
    write(res)


def write(res):
    f = lambda x: f"{x[0]:.3f} [{x[1]:.3f}, {x[2]:.3f}]"
    L = ["# Triage prototype vs published benchmarks", "",
         f"Our numbers: Yale test split, visits with an admit or discharge disposition (n = {res['n_test']}, "
         f"admission rate {res['admission_rate_test']:.1%}); models fitted on the 20% dev split (n = {res['n_dev']}). "
         "Published numbers are copied from the papers.", "",
         "## 1. Admission prediction (AUROC): Hong 2018 (same data) and Xie 2022 (MIMIC-IV-ED)", "",
         "| Model | Data | AUROC [95% CI] |", "|---|---|---|"]
    for k, v in PUBLISHED.items():
        L.append(f"| {k} | published | {v} |")
    for k, v in res["auroc"].items():
        L.append(f"| {k} | ours, Yale test | {f(v)} |")
    L += ["", "## 2. SYS as a referral decision for admission (one operating point)", "",
          "| Arm | n | Sensitivity | Specificity | PPV | NPV |", "|---|---|---|---|---|---|"]
    for arm in ("a_kiosk_vitals_red_flags", "b_with_devices"):
        r = res[f"SYS_{arm}_refer_vs_admission"]
        L.append(f"| {arm} | {r['n']} | {r['sensitivity']:.3f} | {r['specificity']:.3f} | {r['ppv']:.3f} | "
                 f"{r['npv']:.3f} |")
    L += ["", "Published operating points for hospitalization (Xie 2022, MIMIC-IV-ED): GB sensitivity 0.743 / "
          "specificity 0.743; ESI 0.582 / 0.784; NEWS2 0.519 / 0.563.", "",
          "## 3. Correct level per reference class: Semigran 2015 (symptom checkers, vignettes)", "",
          "| System | Urgent / emergent | See a doctor / non-emergent | Self-care | Overall |", "|---|---|---|---|---|",
          "| Semigran 2015: 23 symptom checkers (published) | 0.80 | 0.55 | 0.33 | 0.57 |"]
    for k, v in res["correct_level_per_reference_class"].items():
        L.append(f"| {k} (ours, Yale ED test) | {v['urgent']:.3f} | {v['see_doctor']:.3f} | {v['self_care']:.3f} | "
                 f"{v['overall']:.3f} |")
    L += ["", "## How comparable is this?", "",
          "- Hong 2018 is the same dataset and outcome; our split (20% train / 80% test) differs from theirs "
          "(80 / 10 / 10), and they used XGBoost / LR / DNN, we use LightGBM.",
          "- Xie 2022 is a different hospital system (MIMIC-IV-ED); only the pattern is comparable, not the numbers.",
          "- Semigran 2015 used 45 written vignettes with physician-set triage levels, not ED visits labelled by ESI; "
          "our 'self-care' class is ESI 4-5 discharged, which is not the same as a self-care vignette.",
          "- Admission is not the kiosk's target (the kiosk decides whether to see a doctor, not whether to admit); it "
          "is used because it is what the published benchmarks report."]
    (OUT / "COMPARISON.md").write_text("\n".join(L), encoding="utf-8")
    print("->", OUT / "COMPARISON.md")


if __name__ == "__main__":
    main()
