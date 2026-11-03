"""Decision benchmark on ED data (prototype version of brief P5): train the reference models on the Yale dev split,
then test SYS (the rule engine) and the baselines on the held-out Yale test split and on the MIMIC-IV-ED Demo.

    python -m triage.bench.run_bench [--llm-n 210] [--noise-n 20000] [--draws 10]     (from reasoning_model/src)
    -> results/triage/bench_results.json, results/triage/REPORT.md, results/triage/d5_tree_rules.txt

Visits without an ESI level are dropped. Visits without a triage heart rate are excluded from the sensor arms (the
kiosk would retake); their count is reported. Split: 20% dev / 80% test, random by visit, seed 0 (the Yale data has
no patient or date column). Only aggregates are written.
"""
import argparse
import json
import time

import numpy as np
import pandas as pd

from triage.bench import baselines as B
from triage.bench import ed_cases as E
from triage.bench import metrics as M
from triage.bench import mimic_ed, yale
from triage.evidence import ROOT
from triage.rules_engine import load_config

OUT = ROOT / "results" / "triage"
RF_ITEMS = load_config()["red_flags"]["urgent_items"] + ["self_harm"]      # follows red_flags.yaml
KIOSK_X, DEVICE_X = ("hr", "rr", "temp_c"), ("hr", "rr", "temp_c", "spo2", "sbp", "dbp")


def prepare(df):
    df = df[df["esi"].notna()].copy()
    df["ref"] = [E.reference(e, a) for e, a in zip(df["esi"], df["admitted"])]
    return df


def run_sys(df, arm, cfg, noise=None, seed=0):
    rng = np.random.default_rng(seed)
    acfg = E.arm_config(cfg, arm)
    res = [E.sys_decision(c, arm, acfg, rng, noise) for c in df.to_dict("records")]
    return (np.array([r[0] for r in res], object), np.array([r[1] for r in res], object),
            np.array([r[2] for r in res], bool))


def table(levels, df):
    return M.decision_table(levels, df["ref"].values, df["admitted"].values)


def paired(name_a, lv_a, name_b, lv_b, df):
    urgent = df["ref"].values == 3
    miss_a, miss_b = lv_a[urgent] != "URGENT", lv_b[urgent] != "URGENT"
    return {"a": name_a, "b": name_b, "mcnemar_urgent_misses": M.mcnemar(miss_a, miss_b),
            "urgent_sens_diff_a_minus_b": M.bootstrap_diff(~miss_a, ~miss_b, n_boot=500)}


def fmt_ci(x):
    return "n/a" if x is None or np.isnan(x[0]) else f"{x[0]:.3f} [{x[1]:.3f}, {x[2]:.3f}]"


def main(a):
    t0 = time.perf_counter()
    cfg = load_config()
    OUT.mkdir(parents=True, exist_ok=True)
    R = {"config": {"rules": cfg["rules"]["version"], "rules_status": cfg["rules"]["status"],
                    "margins_status": cfg["ranges"]["error_margins"]["status"], "seed": 0}}

    # ------------------------------------------------ data and split
    ya = prepare(yale.load())
    rng = np.random.default_rng(0)
    is_dev = rng.random(len(ya)) < 0.2
    dev, test = ya[is_dev], ya[~is_dev]
    test_s = test[test["hr"].notna()]
    R["yale"] = {"n_visits_with_esi": len(ya), "n_dev": len(dev), "n_test": len(test),
                 "n_test_with_hr": len(test_s), "test_without_hr_share": float(test["hr"].isna().mean()),
                 "ref_counts_test_with_hr": {E.REF_NAMES[k]: int(v) for k, v in
                                             test_s["ref"].value_counts().sort_index().items()},
                 "complaint_maps_to_red_flag": float(test_s["red_flags"].map(bool).mean()),
                 "urgent_complaint_maps_to_red_flag":
                     float(test_s.loc[test_s.ref == 3, "red_flags"].map(bool).mean())}
    print(f"yale: dev {len(dev)}, test {len(test)} ({len(test_s)} with HR)", flush=True)

    # ------------------------------------------------ train D5 (depth-3 tree) and the LightGBM reference on dev
    dev_s = dev[dev["hr"].notna()]
    models = {}
    for tag, cols in (("kiosk", KIOSK_X), ("devices", DEVICE_X)):
        Xd = B.features(dev_s, RF_ITEMS, cols)
        models[f"D5_tree_{tag}"] = B.fit_tree(Xd, dev_s["ref"].astype(int))
        models[f"ML_lgbm_{tag}"] = B.fit_lgbm(Xd, dev_s["ref"].astype(int))
        if tag == "kiosk":
            (OUT / "d5_tree_rules.txt").write_text(B.tree_rules(models["D5_tree_kiosk"], Xd.columns))
    print(f"trained D5 + LightGBM on {len(dev_s)} dev visits ({time.perf_counter() - t0:.0f}s)", flush=True)

    def model_levels(df, name):
        cols = KIOSK_X if name.endswith("kiosk") else DEVICE_X
        return B.predict_levels(models[name], B.features(df, RF_ITEMS, cols))

    # ------------------------------------------------ Yale test: SYS arms (exact readings) + baselines
    lv, Ry = {}, {}
    for arm in E.ARMS:                                   # all arms on the same visits, so comparisons are paired
        df = test_s
        lv[arm], rules, remeas = run_sys(df, arm, cfg)
        Ry[f"SYS_{arm}"] = {**table(lv[arm], df), "remeasure_share": float(remeas.mean()),
                            "rule_share": pd.Series(rules).value_counts(normalize=True).round(4).to_dict()}
        print(f"SYS {arm}: {fmt_ci(Ry[f'SYS_{arm}']['urgent_sensitivity'])} ({time.perf_counter() - t0:.0f}s)",
              flush=True)
    lv["D0"] = B.d0_always_refer(test_s)
    lv["D3_news2_kiosk"] = B.d3_news2(test_s, use=("rr", "hr", "temp_c"))
    lv["D3_news2_devices"] = B.d3_news2(test_s)
    for name in models:
        lv[name] = model_levels(test_s, name)
    for name in ("D0", "D3_news2_kiosk", "D3_news2_devices", *models):
        Ry[name] = table(lv[name], test_s)
    sa = lv["a_kiosk_vitals_red_flags"]
    R["yale_test"] = Ry
    R["yale_paired_vs_SYS_a"] = [paired("SYS_a", sa, n, lv[n], test_s) for n in
                                 ("c_vitals_only", "d_red_flags_only", "D3_news2_kiosk", "D5_tree_kiosk",
                                  "ML_lgbm_kiosk")
                                 if len(lv[n]) == len(sa)]
    urgent = test_s["ref"] == 3
    R["yale_urgent_all_kiosk_vitals_normal"] = float(np.mean([E.all_kiosk_vitals_normal(c, cfg) for c in
                                                              test_s[urgent].to_dict("records")]))
    sub = {}
    age_grp = pd.cut(test_s["age"], [17, 39, 64, 200], labels=["18-39", "40-64", "65+"])
    for col, groups in (("sex", test_s["sex"]), ("age", age_grp)):
        for g in pd.unique(groups.dropna()):
            m = (groups == g).values
            if m.sum() >= 30:
                sub[f"{col}={g}"] = {"n": int(m.sum()), "urgent_sensitivity": table(sa[m], test_s[m])[
                    "urgent_sensitivity"], "admitted_told_self_care": table(sa[m], test_s[m])[
                    "admitted_told_self_care"]}
    R["yale_subgroups_SYS_a"] = sub

    # ------------------------------------------------ kiosk-like noise (placeholder margins), subsample
    noise_df = test_s.sample(min(a.noise_n, len(test_s)), random_state=0)
    Rn = {}
    for arm in ("a_kiosk_vitals_red_flags", "b_with_devices"):
        draws = []
        for d in range(a.draws):
            lvl, _, rem = run_sys(noise_df, arm, cfg, noise="kiosk", seed=d)
            t = table(lvl, noise_df)
            draws.append({"urgent_sensitivity": t["urgent_sensitivity"][0],
                          "admitted_told_self_care": t["admitted_told_self_care"][0],
                          "self_care_rate_low_acuity": t["self_care_rate_low_acuity"][0],
                          "remeasure_share": float(rem.mean())})
        exact = table(run_sys(noise_df, arm, cfg)[0], noise_df)
        Rn[arm] = {"n": len(noise_df), "draws": a.draws,
                   "exact": {k: exact[k][0] for k in ("urgent_sensitivity", "admitted_told_self_care",
                                                      "self_care_rate_low_acuity")},
                   "noisy_mean": {k: float(np.mean([d[k] for d in draws])) for k in draws[0]},
                   "noisy_min_max": {k: [float(np.min([d[k] for d in draws])), float(np.max([d[k] for d in draws]))]
                                     for k in draws[0]}}
    R["yale_kiosk_noise"] = Rn
    print(f"noise arms done ({time.perf_counter() - t0:.0f}s)", flush=True)

    # ------------------------------------------------ D4 LLM alone vs SYS on a stratified sample
    if a.llm_n:
        per = a.llm_n // 3
        samp = pd.concat([test_s[test_s.ref == r].sample(min(per, int((test_s.ref == r).sum())), random_state=0)
                          for r in (3, 2, 1)])
        try:
            llm_lv, lat = B.d4_llm(samp, vitals=KIOSK_X)
            sys_lv = run_sys(samp, "a_kiosk_vitals_red_flags", cfg)[0]
            R["yale_llm_sample"] = {"n": len(samp), "design": f"{per} per reference level (stratified)",
                                    "D4_llm_alone": table(llm_lv, samp), "SYS_a": table(sys_lv, samp),
                                    "invalid_share": float(np.mean(llm_lv == "INVALID")),
                                    "latency_s_p50_p95": [float(np.percentile(lat, 50)),
                                                          float(np.percentile(lat, 95))],
                                    "paired": paired("SYS_a", sys_lv, "D4_llm_alone", llm_lv, samp)}
        except OSError as e:
            R["yale_llm_sample"] = {"skipped": f"Ollama not reachable: {e}"}
        print(f"LLM sample done ({time.perf_counter() - t0:.0f}s)", flush=True)

    # ------------------------------------------------ external: MIMIC-IV-ED Demo
    mi = prepare(mimic_ed.load(cfg=cfg))
    mi = mi[~E.mimic_dev_mask(mi)]      # the 20% dev subjects are used for rule derivation (derive/), never tested
    mi_s = mi[mi["hr"].notna()]
    Rm = {"n_stays_with_esi": len(mi), "n_with_hr": len(mi_s), "n_patients": int(mi_s.patient_id.nunique()),
          "ref_counts_with_hr": {E.REF_NAMES[k]: int(v) for k, v in mi_s["ref"].value_counts().sort_index().items()},
          "complaint_maps_to_red_flag": float(mi_s["red_flags"].map(bool).mean())}
    mlv = {}
    for arm in E.ARMS:
        df = mi_s
        mlv[arm] = run_sys(df, arm, cfg)[0]
        Rm[f"SYS_{arm}"] = table(mlv[arm], df)
    for name, f in (("D0", B.d0_always_refer), ("D3_news2_kiosk", lambda d: B.d3_news2(d, ("rr", "hr", "temp_c"))),
                    ("D3_news2_devices", B.d3_news2)):
        Rm[name] = table(f(mi_s), mi_s)
    for name in models:
        Rm[name] = table(model_levels(mi_s, name), mi_s)
    if a.llm_n:
        try:
            llm_lv, lat = B.d4_llm(mi_s, vitals=KIOSK_X)
            Rm["D4_llm_alone"] = {**table(llm_lv, mi_s), "latency_s_p50_p95": [float(np.percentile(lat, 50)),
                                                                                float(np.percentile(lat, 95))]}
        except OSError as e:
            Rm["D4_llm_alone"] = {"skipped": str(e)}
    sm = mlv["a_kiosk_vitals_red_flags"]
    urg = mi_s["ref"].values == 3
    Rm["urgent_sens_patient_bootstrap_SYS_a"] = M.bootstrap_diff((sm[urg] == "URGENT"), np.zeros(urg.sum()),
                                                                 groups=mi_s["patient_id"].values[urg], n_boot=1000)
    R["mimic_demo"] = Rm
    R["runtime_s"] = round(time.perf_counter() - t0, 1)

    (OUT / "bench_results.json").write_text(json.dumps(R, indent=1, default=float))
    write_report(R)
    print(f"done in {R['runtime_s']}s -> {OUT}")


ROWS = [("SYS_a_kiosk_vitals_red_flags", "SYS a: kiosk vitals + red flags"),
        ("SYS_b_with_devices", "SYS b: + BP / SpO2 devices"),
        ("SYS_c_vitals_only", "SYS c = D1: vitals only"), ("SYS_d_red_flags_only", "SYS d = D2: red flags only"),
        ("D0", "D0: always refer"), ("D3_news2_kiosk", "D3: NEWS2, kiosk vitals"),
        ("D3_news2_devices", "D3: NEWS2, all vitals"), ("D5_tree_kiosk", "D5: depth-3 tree, kiosk inputs (trained)"),
        ("D5_tree_devices", "D5: depth-3 tree, all inputs (trained)"),
        ("ML_lgbm_kiosk", "ML: LightGBM, kiosk inputs (trained)"),
        ("ML_lgbm_devices", "ML: LightGBM, all inputs (trained)"), ("D4_llm_alone", "D4: local LLM alone")]


def decision_rows(block):
    lines = ["| System | n | URGENT sensitivity [95% CI] | Admitted told SELF-CARE | Low-acuity → SELF-CARE "
             "| Under-triage | Over-triage | Weighted κ |", "|---|---|---|---|---|---|---|---|"]
    for key, label in ROWS:
        t = block.get(key)
        if not t or "n" not in t:
            continue
        lines.append(f"| {label} | {t['n_decided']} | {fmt_ci(t['urgent_sensitivity'])} | "
                     f"{fmt_ci(t['admitted_told_self_care'])} | {fmt_ci(t['self_care_rate_low_acuity'])} | "
                     f"{t['under_triage']:.3f} | {t['over_triage']:.3f} | {t['weighted_kappa']:.3f} |")
    return "\n".join(lines)


def write_report(R):
    y, m = R["yale"], R["mimic_demo"]
    sa = R["yale_test"]["SYS_a_kiosk_vitals_red_flags"]
    L = [
        "# Triage prototype: decision benchmark on ED data",
        "",
        f"Rules {R['config']['rules']} (**{R['config']['rules_status']}**, not clinician-reviewed); device error "
        f"margins **{R['config']['margins_status']}**. Research prototype; not a medical device.",
        "",
        "Reference: URGENT = ESI 1-2; SEE A DOCTOR = ESI 3 (or ESI 4-5 admitted); SELF-CARE-compatible = ESI 4-5 "
        "discharged. *Admitted told SELF-CARE* is the main safety miss for a kiosk; *URGENT sensitivity* is the "
        "brief's primary metric. CIs are exact (Clopper-Pearson).",
        "",
        "## Yale ED, held-out test split",
        "",
        f"{y['n_visits_with_esi']} visits with ESI; dev {y['n_dev']} (training of D5 / ML only), test {y['n_test']}, "
        f"of which {y['n_test_with_hr']} have a triage heart rate (sensor arms; {y['test_without_hr_share']:.1%} "
        f"without would be a RETAKE). Test reference counts: {y['ref_counts_test_with_hr']}. Chief complaint maps to a "
        f"red flag in {y['complaint_maps_to_red_flag']:.1%} of visits and {y['urgent_complaint_maps_to_red_flag']:.1%}"
        " of urgent visits.",
        "",
        decision_rows(R["yale_test"]),
        "",
        f"Urgent visits with **all kiosk vitals in the normal range**: {R['yale_urgent_all_kiosk_vitals_normal']:.1%} "
        "(only a red-flag question can catch these).",
        "",
        "SYS a, rule that set the level: " + ", ".join(f"{k} {v:.1%}" for k, v in sa["rule_share"].items()) +
        f"; re-measured {sa['remeasure_share']:.1%}.",
        "",
        "### Paired comparisons with SYS a (urgent misses, same visits)",
        "",
        "| vs | Only SYS a missed | Only other missed | McNemar p | Sensitivity difference SYS a − other [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for p in R["yale_paired_vs_SYS_a"]:
        d = p["urgent_sens_diff_a_minus_b"]
        L.append(f"| {p['b']} | {p['mcnemar_urgent_misses']['only_a_missed']} | "
                 f"{p['mcnemar_urgent_misses']['only_b_missed']} | {p['mcnemar_urgent_misses']['p']:.2g} | "
                 f"{d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}] |")
    L += ["", "### Subgroups (SYS a)", "", "| Group | n | URGENT sensitivity | Admitted told SELF-CARE |",
          "|---|---|---|---|"]
    for g, s in R["yale_subgroups_SYS_a"].items():
        L.append(f"| {g} | {s['n']} | {fmt_ci(s['urgent_sensitivity'])} | {fmt_ci(s['admitted_told_self_care'])} |")
    L += ["", "### Kiosk-like measurement noise (placeholder margins)", "",
          "| Arm | n × draws | Metric | Exact ED values | Noisy mean (min–max over draws) |", "|---|---|---|---|---|"]
    for arm, r in R["yale_kiosk_noise"].items():
        for k in ("urgent_sensitivity", "admitted_told_self_care", "self_care_rate_low_acuity"):
            lo, hi = r["noisy_min_max"][k]
            L.append(f"| {arm} | {r['n']} × {r['draws']} | {k} | {r['exact'][k]:.3f} | "
                     f"{r['noisy_mean'][k]:.3f} ({lo:.3f}–{hi:.3f}) |")
        L.append(f"| {arm} | | REMEASURE share | | {r['noisy_mean']['remeasure_share']:.3f} |")
    ls = R.get("yale_llm_sample", {})
    if "D4_llm_alone" in ls:
        L += ["", f"### Local LLM alone (D4) vs SYS a, stratified sample (n = {ls['n']}, {ls['design']})", "",
              decision_rows({"SYS_a_kiosk_vitals_red_flags": ls["SYS_a"], "D4_llm_alone": ls["D4_llm_alone"]}), "",
              f"LLM invalid outputs {ls['invalid_share']:.1%}; latency p50 / p95 {ls['latency_s_p50_p95'][0]:.2f} / "
              f"{ls['latency_s_p50_p95'][1]:.2f} s. Sample sensitivities are not population estimates (stratified)."]
    elif ls:
        L += ["", f"D4 skipped: {ls.get('skipped')}"]
    b = m["urgent_sens_patient_bootstrap_SYS_a"]
    L += ["", "## MIMIC-IV-ED Demo (external, never used for training or tuning)", "",
          f"{m['n_stays_with_esi']} stays with ESI ({m['n_with_hr']} with HR, {m['n_patients']} patients); reference "
          f"counts {m['ref_counts_with_hr']}. Complaint maps to a red flag in {m['complaint_maps_to_red_flag']:.1%}. "
          f"Very few low-acuity stays, so specificity-type metrics are not estimable here.", "",
          decision_rows(m), "",
          f"SYS a URGENT sensitivity with a patient-level bootstrap CI: {b[0]:.3f} [{b[1]:.3f}, {b[2]:.3f}].", "",
          "## Caveats", "",
          "- ED populations overstate urgency compared with kiosk users; ESI is a nurse rating, not an outcome.",
          "- The kiosk cannot measure BP / SpO2 without devices (arm b).",
          "- Context questions and PHQ-2 / GAD-2 rules are untested here (no such data in ED records).",
          "- Red flags come from the chief complaint (a proxy for the kiosk questions); breathlessness complaints are "
          "mapped to *severe* breathlessness, which overstates that red flag.",
          "- Yale split is random by visit (no patient / date column): repeat visits of one person can fall in both "
          "dev and test, which can only flatter the trained D5 / ML references, not the untrained rule engine.",
          "- Error margins are placeholders (P6 not run), so the noise arm shows sensitivity to noise, not the "
          "kiosk's real behaviour.",
          "- Rules are drafts, not yet reviewed by a clinician, and were not tuned on this data; D5 / ML are "
          "trained references and are never deployed.",
          f"\nRuntime {R['runtime_s']} s."]
    (OUT / "REPORT.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-n", type=int, default=210, help="stratified Yale sample for D4; 0 = skip the LLM")
    ap.add_argument("--noise-n", type=int, default=20000)
    ap.add_argument("--draws", type=int, default=10)
    main(ap.parse_args())
