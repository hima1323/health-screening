"""Triage Lab: run the expert system on sample data and see every reading, decision and reason (Streamlit, local).

Tabs
  1. Benchmark a dataset   upload a CSV / Excel file (format: templates/benchmark_dataset_template.csv) or pick a
                           built-in one (template sample, draft vignettes, Yale ED test sample, MIMIC-IV-ED Demo test
                           subjects); metrics vs the baselines, the confusion matrix, then any single case in detail
  2. One case              type readings and answers, see the decision, the readings against their ranges, the
                           reasoning chain and the explanation
  3. Face video -> HR      the rPPG model (rppg1, CVPR Lab P4) reads the heart rate from a face video; the reading
                           can be used in tab 2
  4. Saved results         the ED benchmark, vignette and reasoning reports and the rPPG comparison tables

Draft rules (not clinician-approved), synthetic / sample data only. Nothing leaves this machine; the LLM is local.

    .venv\\Scripts\\streamlit run src\\triage\\lab_app.py --server.port 8503        (from reasoning_model/; start_lab.bat)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # streamlit runs this file as a script

import numpy as np
import pandas as pd
import streamlit as st

from triage.bench import dataset_bench as DB
from triage.bench.vignettes import fmt_ci, load_vignettes, report, run, to_record
from triage.evidence import ROOT
from triage.explainer import LABELS, NAMES, explain
from triage.reasoning_chain import apply
from triage.rules_engine import load_config, rule_table

RPPG = ROOT.parent / "rppg1"
COLORS = {"URGENT": "#c62828", "SEE_DOCTOR_SOON": "#ef6c00", "SELF_CARE": "#2e7d32", "RETAKE": "#546e7a",
          "REMEASURE": "#1565c0", "NOT_SUITABLE": "#6a1b9a"}
ARM_NAMES = {"SYS": "Expert system (rules)", "D0_always_refer": "D0 always refer",
             "D1_vitals_only": "D1 readings only", "D2_red_flags_only": "D2 warning signs only",
             "D3_news2": "D3 NEWS2 score", "D4_llm": "D4 LLM alone"}

st.set_page_config(page_title="Triage Lab", page_icon="🧪", layout="wide")
cfg = st.cache_resource(load_config)()
S = st.session_state


# ---------------------------------------------------------------- built-in datasets

@st.cache_data(show_spinner="Loading the dataset…")
def builtin(name, n):
    """-> DataFrame in the dataset_bench column format."""
    if name == "Template sample (8 made-up cases)":
        return DB.read(ROOT / "templates" / "benchmark_dataset_template.csv")
    if name.startswith("Yale"):
        from triage.bench import yale
        df = yale.load()
        df = df[df["esi"].notna() & df["hr"].notna()]
        df = df[np.random.default_rng(0).random(len(df)) >= 0.2]          # the benchmark's test split (seed 0)
        df = df[(df["age"] >= 18) & (df["age"] <= 65)].sample(min(n, len(df)), random_state=0)
    else:
        from triage.bench import ed_cases, mimic_ed
        df = mimic_ed.load(cfg=cfg)
        df = df[df["esi"].notna()]
        df = df[~ed_cases.mimic_dev_mask(df)]                              # never the rule-derivation subjects
    flags = cfg["red_flags"]["urgent_items"] + ["self_harm"]
    out = pd.DataFrame({"case_id": df["case_id"].astype(str), "hr": df["hr"], "rr": df["rr"], "temp_c": df["temp_c"],
                        "spo2": df["spo2"], "sbp": df["sbp"], "dbp": df["dbp"], "esi": df["esi"],
                        "admitted": df["admitted"].map({True: "yes", False: "no"}),
                        "complaint": df["complaint"]})
    for f in flags:
        out[f] = df["red_flags"].map(lambda r, f=f: "yes" if f in r else "no").values
    return out.reset_index(drop=True)


def vignettes_df():
    rows = []
    for v in load_vignettes():
        r = {"case_id": v["id"], "age": v.get("age"), "complaint": v.get("narrative", "")}
        for name, x in v["measurements"].items():
            col = {"heart_rate": "hr", "resp_rate": "rr", "temperature": "temp_c"}.get(name, name)
            if x is not None:
                xs = x if isinstance(x, list) else [x]
                r[col], r[f"{col}_2"] = xs[0], xs[-1]
        for name, x in (v.get("measurements_after_rest") or {}).items():
            col = {"heart_rate": "hr", "resp_rate": "rr", "temperature": "temp_c"}.get(name, name)
            if x is not None:
                r[f"{col}_rest"] = x[0] if isinstance(x, list) else x
        for name, q in (v.get("quality") or {}).items():
            r[f"quality_{name}"] = q
        r.update(v["answers"])
        r.update({k.lower(): s for k, s in (v.get("scores") or {}).items()})
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- shared views

def badge(level, size="1.3rem"):
    st.markdown(f"<div style='background:{COLORS.get(level, '#333')};color:white;padding:12px 18px;border-radius:10px;"
                f"font-size:{size};font-weight:700'>{LABELS.get(level, level)}</div>", unsafe_allow_html=True)


def final_record(v):
    rec = apply(to_record(v, cfg), cfg)
    first = rec["decision"]
    if first["level"] == "REMEASURE":
        rec = apply(to_record(v, cfg, after_rest=True), cfg)
    return rec, first


def show_case(rec, first=None, use_llm=False, key=""):
    ch = {s["step"]: s for s in rec["chain"]}
    badge(rec["decision"]["level"])
    if first is not None and first["level"] == "REMEASURE":
        st.info(f"First decision: rest and measure again ({first['rule_id']}). Shown: the decision after the second "
                "measurement.")
    st.write(f"**Rule that decided:** `{rec['decision']['rule_id']}`: {rec['decision']['reason']}")
    also = [m["rule_id"] for m in rec["decision"]["also_matched"]]
    if also:
        st.caption("Also matched (lower in the order): " + ", ".join(also))
    st.markdown("##### Readings")
    rows = []
    for i in ch["interpretation"]["items"]:
        rng = lambda r: "" if r is None else f"{r[0] if r[0] is not None else '…'} – {r[1] if r[1] is not None else '…'}"
        rows.append({"measure": NAMES.get(i["name"], i["name"]), "readings": ", ".join(f"{x:g}" for x in i["readings"])
                     or "not measured", "unit": i["unit"], "normal range": rng(i.get("normal")),
                     "urgent if outside": rng(i.get("urgent")), "error margin": i["margin"], "quality": i["quality"],
                     "status": {"in": "✅ in range", "borderline": "⚠️ near the limit", "out": "🔴 outside",
                                "not_usable": "unclear", "not_measured": "not measured"}.get(i["status"], i["status"])})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    ans = [a for a in rec["answers"] if a["answer"] not in ("no",)]
    c1.markdown("##### Answers that matter")
    c1.write("\n".join(f"- `{a['id']}` {a['item'].replace('_', ' ')}: **{a['answer']}**" for a in ans) or "none")
    if rec["scores"]:
        c1.write(", ".join(f"{s['name']} = {s['value']:g}" for s in rec["scores"]))
    c2.markdown("##### Uncertainty")
    c2.write("\n".join(f"- {u['text']}" + (f": {', '.join(u['names'])}" if u.get("names") else "")
                       for u in ch["uncertainty"]["items"]) or "none")
    card, log = explain(rec, cfg, use_llm=use_llm)
    st.markdown("##### What the person would read")
    st.write(card["summary"])
    st.write("\n".join(f"- {r}" for r in card["reasons"]))
    st.success(card["advice"]) if rec["decision"]["level"] == "SELF_CARE" else st.warning(card["advice"])
    if card["contacts"]:
        st.error(" · ".join(f"{c['name']}: **{c['number']}**" for c in card["contacts"]))
    st.caption(f"Text: {log['source']} ({log['seconds']} s). {card['disclaimer']}")
    with st.expander("Full evidence record and reasoning chain (JSON)"):
        st.json(json.loads(json.dumps(rec, default=str)))


# ---------------------------------------------------------------- page

st.title("🧪 Triage Lab")
st.caption("Run the rule-based triage system on sample data and see every reading and reason. Draft rules, not "
           "clinician-approved; research prototype, not a medical device.")
t_try, t_data, t_case, t_video, t_saved = st.tabs(["0 · Try a sample", "1 · Benchmark a dataset", "2 · One case",
                                                   "3 · Face video → heart rate", "4 · Saved results"])

SAMPLE_SETS = ["Draft vignettes (22 hand-written cases)", "Template sample (8 made-up cases)",
               "Yale ED test split (real ED cases, ages 18-65)", "MIMIC-IV-ED Demo (real ED cases, test subjects)"]


@st.cache_data(show_spinner="Loading the samples…")
def sample_cases(src):
    """-> (DataFrame of the raw inputs, {case_id: vignette}) for a built-in sample set."""
    df = vignettes_df() if src.startswith("Draft") else builtin(src, 2000)
    vigs, _ = DB.to_vignettes(df, cfg)
    return df, {v["id"]: v for v in vigs}


with t_try:
    st.write("Pick a ready-made sample, no upload needed. The system's decision, its reasons and the explanation "
             "appear straight away.")
    sset = st.selectbox("Sample set", SAMPLE_SETS)
    sdf, svigs = sample_cases(sset)
    ids = [str(i) for i in sdf["case_id"]]
    sid = st.selectbox("Case", ids, format_func=lambda i: f"{i}  ·  {str(svigs[i].get('narrative') or '')[:70]}")
    v = svigs[sid]
    UNITS = {"heart_rate": "bpm", "resp_rate": "breaths/min", "temperature": "°C", "spo2": "%", "sbp": "mmHg",
             "dbp": "mmHg"}
    st.markdown("### 1 · Input")
    st.caption("Everything the system is given for this person.")
    who = st.columns(3)
    who[0].metric("Age", f"{v['age']:g}" if v.get("age") == v.get("age") and v.get("age") is not None else "unknown")
    who[1].metric("Mood score PHQ-2 (0-6)", f"{(v.get('scores') or {}).get('PHQ2', '-')}")
    who[2].metric("Worry score GAD-2 (0-6)", f"{(v.get('scores') or {}).get('GAD2', '-')}")
    note = v.get("narrative")
    if note and str(note).lower() != "nan":
        st.markdown(f"**Complaint:** {note}")
    st.markdown("**Measurements** (reading 1, reading 2)")
    mrows = []
    for name, x in v["measurements"].items():
        xs = x if isinstance(x, list) else [x]
        if x is not None and len(xs):
            mrows.append({"Measurement": NAMES.get(name, name).capitalize(), "Reading 1": xs[0], "Reading 2": xs[-1],
                          "Unit": UNITS.get(name, "")})
    if mrows:
        st.dataframe(pd.DataFrame(mrows), hide_index=True, width="stretch")
    else:
        st.write("No measurements.")
    yes = [k.replace("_", " ") for k, a in v["answers"].items() if str(a).lower() in ("yes", "not sure")]
    st.markdown("**Answered yes:** " + (", ".join(yes) if yes else "none of the warning signs or context questions"))
    ref = v["clinician_labels"].get("consensus")

    st.markdown("### 2 · Output")
    llm_try = st.toggle("Write the explanation with the local LLM", key="llm_try")
    rec, first = final_record(v)
    level = rec["decision"]["level"]
    card, _log = explain(rec, cfg, use_llm=llm_try)
    badge(level)
    st.markdown(f"**Why:** {rec['decision']['reason']}")
    if first["level"] == "REMEASURE":
        st.caption("First result was 'rest and measure again'; this is the decision after the second measurement.")
    if card["reasons"]:
        st.markdown("\n".join(f"- {r}" for r in card["reasons"][:4]))
    st.success(card["advice"]) if level == "SELF_CARE" else st.warning(card["advice"])
    if card["contacts"]:
        st.error(" · ".join(f"{c['name']}: **{c['number']}**" for c in card["contacts"]))
    if ref:
        st.caption(("✅ Matches" if level == ref else "⚠️ Differs from") + f" the dataset's reference level: {LABELS.get(ref, ref)}")
    with st.expander("Show full detail (readings vs ranges, uncertainty, reasoning chain)"):
        show_case(rec, first, use_llm=llm_try)


with t_data:
    src = st.radio("Data", ["Upload a file", "Template sample (8 made-up cases)", "Draft vignettes (22, unlabelled)",
                            "Yale ED test split (sample, ages 18-65)", "MIMIC-IV-ED Demo (test subjects)"],
                   horizontal=True)
    df = None
    if src == "Upload a file":
        up = st.file_uploader("CSV or Excel, one row per case (columns: see the template below)",
                              type=["csv", "xlsx", "xls"])
        st.download_button("Download the column template", (ROOT / "templates" /
                                                             "benchmark_dataset_template.csv").read_bytes(),
                           "benchmark_dataset_template.csv")
        if up:
            p = Path(tempfile.mkdtemp()) / up.name
            p.write_bytes(up.getvalue())
            df = DB.read(p)
    elif src.startswith("Draft"):
        df = vignettes_df()
    elif src.startswith("Yale"):
        n = st.select_slider("Cases", [500, 2000, 5000, 20000], value=2000)
        df = builtin(src, n)
    else:
        df = builtin(src, 0)
    with_llm = st.checkbox("Also run D4: the local LLM deciding alone (slow: ~1 s per case)")
    if df is not None:
        st.caption(f"{len(df)} rows, columns: {', '.join(df.columns[:25])}{' …' if len(df.columns) > 25 else ''}")
        if st.button("Run the benchmark", type="primary"):
            with st.spinner("Running the rules and the baselines…"):
                vigs, cols = DB.to_vignettes(df, cfg)
                res_df = run(vigs, cfg, with_llm=with_llm)
                S["bench"] = {"vigs": {v["id"]: v for v in vigs}, "df": res_df, "res": report(res_df), "cols": cols,
                              "src": src}
    if "bench" in S:
        B = S["bench"]
        res, res_df = B["res"], B["df"]
        st.subheader(f"Results: {B['src']}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Cases", res["n_vignettes"])
        m2.metric("With a reference level", res["n_labelled"])
        m3.metric("Re-measured once", res["sys_remeasured"])
        st.bar_chart(pd.Series(res["sys_levels"], name="cases"), horizontal=True, height=200)
        if res["n_labelled"]:
            rows = [{"method": ARM_NAMES.get(a, a), "URGENT caught (95% CI)": fmt_ci(m["urgent_sensitivity"]),
                     "under-triage": round(m["under_triage"], 3), "over-triage": round(m["over_triage"], 3),
                     "weighted kappa": round(m["weighted_kappa"], 3), "exact agreement": round(m["exact_agreement"], 3)}
                    for a, m in res["arms"].items()]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Reference: the dataset's expected level, or ESI 1-2 = URGENT, ESI 3 or admitted = SEE A DOCTOR, "
                       "else SELF-CARE. Under-triage = system level below the reference (the safety miss).")
            cm = pd.DataFrame(res["arms"]["SYS"]["confusion_ref_rows_sys_cols"]).T
            st.write("**Confusion matrix, expert system** (rows = reference, columns = system)")
            st.dataframe(cm.loc[:, cm.sum() > 0], width="stretch")
        else:
            st.info("No reference column (expected_level or esi): showing the decisions only.")
        st.write("**Rule that set the level**")
        st.dataframe(res_df["SYS_rule"].value_counts().rename("cases"), width="stretch")
        st.write("**Per case** (pick one below to see its readings and reasons)")
        show = res_df.rename(columns={"label": "reference", "SYS": "system"})
        only_diff = st.checkbox("Only cases where the system differs from the reference")
        if only_diff:
            show = show[show["reference"].notna() & (show["reference"] != show["system"])]
        st.dataframe(show, hide_index=True, width="stretch", height=260)
        st.download_button("Download per-case results (CSV)", res_df.to_csv(index=False).encode(), "cases.csv")
        pick = st.selectbox("Case", list(show["id"])[:5000])
        if pick:
            v = B["vigs"][pick]
            if v.get("narrative"):
                st.caption(f"Complaint / note: {v['narrative']}")
            if v["clinician_labels"].get("consensus"):
                st.caption(f"Reference level: {v['clinician_labels']['consensus']}")
            rec, first = final_record(v)
            show_case(rec, first, use_llm=st.toggle("Write the explanation with the local LLM", key="llm_case"))

with t_case:
    st.write("Two readings per vital (the second is the repeat after 60 s). Leave a vital at 0 = not measured.")
    hr0 = S.get("video_hr")
    c = st.columns(3)
    vit = {}
    for col, (name, unit, d1, lo, hi, step) in zip(c * 2, [("heart_rate", "bpm", hr0 or 72.0, 0.0, 250.0, 1.0),
                                                          ("resp_rate", "/min", 15.0, 0.0, 60.0, 1.0),
                                                          ("temperature", "°C", 36.7, 0.0, 43.0, 0.1),
                                                          ("spo2", "% (oximeter)", 0.0, 0.0, 100.0, 1.0),
                                                          ("sbp", "mmHg (cuff)", 0.0, 0.0, 260.0, 1.0),
                                                          ("dbp", "mmHg (cuff)", 0.0, 0.0, 160.0, 1.0)]):
        with col:
            st.write(f"**{NAMES[name].capitalize()}** ({unit})")
            a = st.number_input("reading 1", lo, hi, float(d1), step, key=f"{name}1")
            b = st.number_input("reading 2", lo, hi, float(d1), step, key=f"{name}2")
            if a > 0:
                vit[name] = [a, b if b > 0 else a]
    if hr0:
        st.caption(f"Heart rate pre-filled from the face video: {hr0:.0f} bpm")
    st.write("**Answers**")
    cols = st.columns(4)
    ans = {}
    items = cfg["red_flags"]["urgent_items"] + ["self_harm"] + \
        list(cfg["questionnaire"]["sections"]["context"]["items"])
    for i, item in enumerate(items):
        if cols[i % 4].toggle(item.replace("_", " "), key=f"t_{item}"):
            ans[item] = "yes"
        else:
            ans[item] = "no"
    a1, a2, a3, a4 = st.columns(4)
    age = a1.number_input("age", 0, 120, 35)
    ans["pregnant"] = a2.selectbox("pregnant", ["no", "yes", "not sure"])
    days = a3.number_input("symptom for how many days (0 = none)", 0, 365, 0)
    phq = a4.slider("PHQ-2 (mood, 0-6)", 0, 6, 0)
    gad = a4.slider("GAD-2 (worry, 0-6)", 0, 6, 0)
    if days:
        ans.update(has_symptom="yes", symptom_duration_days=days)
    use_llm = st.toggle("Write the explanation with the local LLM", key="llm_single")
    if st.button("Decide", type="primary"):
        v = DB.normalise({"id": "manual", "age": age, "measurements": vit, "answers": ans,
                          "scores": {"PHQ2": phq, "GAD2": gad}, "clinician_labels": {}})
        S["single"] = v
    if "single" in S:
        rec, first = final_record(S["single"])
        show_case(rec, first, use_llm=use_llm)

with t_video:
    st.write("Upload a face video (30-60 s, still, even light). The rPPG model reads the heart rate; it can then be "
             "used in tab 2.")
    if not (RPPG / "bench" / "infer.py").exists():
        st.error(f"rPPG code not found at {RPPG}")
    else:
        src = st.radio("Input", ["Dataset sample", "Upload a video"], horizontal=True)
        mname = st.selectbox("rPPG model", ["p4", "p4-12-flip", "p4-12", "physformer"])
        vid = None
        if src == "Upload a video":
            vid = st.file_uploader("Face video", type=["mp4", "avi", "mov", "mkv"])
        else:
            sys.path.insert(0, str(RPPG))
            from bench.infer import BENCH
            from bench.run import load_metas, split_by_subject
            dsn = st.selectbox("Dataset", list(BENCH), format_func=lambda k: {
                "mcd": "MCD-rPPG (held-out test subjects)", "ubfc": "UBFC-rPPG", "mpsc": "MPSC-rPPG"}[k])
            try:
                metas = load_metas(BENCH[dsn])
                metas = split_by_subject(metas, 0.8)[1] if dsn == "mcd" else metas
            except SystemExit as e:
                metas = []
                st.error(str(e))
            if metas:
                m = st.selectbox("Sample", metas, format_func=lambda m: f"{m['video_id']}  ({m['n_frames']} frames, {m['fps']:.0f} fps)")
                if st.button("Run on this sample", type="primary"):
                    import numpy as np
                    from bench.infer import Predictor, pulse
                    from bench.metrics import codec_notch, fft_hr, post_process
                    fr = np.load(Path(m["dir"]) / (m["video_id"] + ".frames.npy"))
                    with st.spinner("Running the model…"):
                        pr = st.cache_resource(Predictor)(mname)
                        w = pulse(pr(fr, m["fps"]), m["fps"])
                        hr = fft_hr(w, m["fps"], codec_notch(m))
                        ref = fft_hr(post_process(np.asarray(m["ppg"]), m["fps"], diff_flag=False), m["fps"])
                    S["video_hr"] = hr
                    half = len(w) // 2
                    S["video_reps"] = [fft_hr(w[:half], m["fps"]), fft_hr(w[half:], m["fps"])] if half >= 160 else [hr, hr]
                    S["video_wave"] = (w, m["fps"], m["face_found"], len(fr))
                    S["video_ref"] = ref
        if vid and st.button("Measure heart rate", type="primary"):
            sys.path.insert(0, str(RPPG))
            from bench.infer import Predictor, pulse, read_faces          # rppg1/bench (not triage.bench)
            from bench.metrics import fft_hr
            p = Path(tempfile.mkdtemp()) / vid.name
            p.write_bytes(vid.getvalue())
            with st.spinner("Reading the face and running the model…"):
                frames, fps, found = read_faces(str(p))
                if frames is None or len(frames) < 160:
                    st.error("The video is too short: at least 160 frames (about 6 s) are needed.")
                else:
                    pr = st.cache_resource(Predictor)(mname)
                    w = pulse(pr(frames, fps), fps)
                    hr = fft_hr(w, fps)
                    half = len(w) // 2
                    reps = [fft_hr(w[:half], fps), fft_hr(w[half:], fps)] if half >= 160 else [hr, hr]
                    S["video_hr"] = hr
                    S["video_reps"] = reps
                    S["video_wave"] = (w, fps, found, len(frames))
                    S.pop("video_ref", None)
        if "video_wave" in S:
            w, fps, found, n = S["video_wave"]
            st.metric("Heart rate", f"{S['video_hr']:.0f} bpm",
                      help="Whole-video FFT peak, as in the benchmark")
            st.caption(f"{n} frames at {fps:.1f} fps; face {'found' if found else 'NOT found (whole frame used)'}; "
                       f"first / second half: {S['video_reps'][0]:.0f} / {S['video_reps'][1]:.0f} bpm")
            if "video_ref" in S and src == "Dataset sample":
                st.metric("Ground-truth HR (oximeter label)", f"{S['video_ref']:.0f} bpm",
                          delta=f"{S['video_hr'] - S['video_ref']:+.1f} bpm error", delta_color="off")
            st.line_chart(pd.DataFrame({"pulse": w[-int(fps * 15):]}), height=180)
            st.info("Open tab 2: the heart rate is pre-filled there (press Decide).")

with t_saved:
    for title, f in (("ED benchmark (Yale + MIMIC-IV-ED Demo)", "REPORT.md"), ("Reasoning benchmark", "reasoning_bench.md")):
        p = ROOT / "results" / "triage" / f
        with st.expander(title, expanded=f == "REPORT.md"):
            st.markdown(p.read_text(encoding="utf-8") if p.exists() else "not run yet")
    vs = ROOT / "results" / "triage" / "vignettes_summary.json"
    with st.expander("Vignette benchmark"):
        st.json(json.loads(vs.read_text(encoding="utf-8")) if vs.exists() else {})
    with st.expander("rPPG model comparison (heart-rate accuracy on MCD, UBFC, MPSC)"):
        for i in (1, 2, 3):
            img = RPPG / "runs" / f"comparison_tables_table{i}.png"
            if img.exists():
                st.image(str(img))
    with st.expander("Rule table"):
        st.dataframe(pd.DataFrame(rule_table(cfg)), hide_index=True, width="stretch")
