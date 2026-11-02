"""Local kiosk prototype UI (Streamlit): upload recordings -> measurement agents -> questions -> rule engine -> result
card and reasoning chain. Runs offline; uploaded files stay in a temporary folder on this machine.

Vitals are never typed in: they come from the recordings (face video -> heart rate, thermal -> temperature and
breathing rate, ECG / finger-PPG file -> heart rate). Only the questionnaire and optional BP cuff / oximeter numbers
are entered. The level comes only from rules_engine.py; the card text comes from the reasoning chain (code).

    .venv\\Scripts\\streamlit run src\\triage\\kiosk_app.py -- --demo        (from reasoning_model/; or start_kiosk_demo.bat)

Without --demo the app refuses to run a session while any rule, range, red flag, message or contact is still a DRAFT
(starter kit safety rule 2); --demo allows the drafts for synthetic and sample data only. Under the card, the
explainer (local LLM, verified; else the deterministic template) puts the reasoning chain into plain words, and a
follow-up chat answers from the session record and the knowledge text only (followup_qa.py).
"""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # streamlit runs this file as a script

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from triage.evidence import ROOT, add_answer, add_measurement, add_score, by_id, new_record
from triage.measure import measure_recordings
from triage.reasoning_chain import apply
from triage.explainer import explain
from triage.followup_qa import answer as followup_answer, load_knowledge
from triage.rules_engine import approval_problems, load_config, rule_table

DEMO = "--demo" in sys.argv

MCD = ROOT / "data" / "public" / "mcd_rppg"
SESSIONS = ROOT.parent / "server" / "data" / "sessions"
SAMPLES = {
    "MCD-rPPG subject 1020, before exercise: face video + ECG": {
        "video": MCD / "video" / "1020_IriunWebcam_before.avi", "contact": MCD / "ecg" / "1020_before.json"},
    "MCD-rPPG subject 1020, after exercise: face video + ECG": {
        "video": MCD / "video" / "1020_IriunWebcam_after.avi", "contact": MCD / "ecg" / "1020_after.json"},
    "MCD-rPPG subject 1020, before exercise: face video only": {"video": MCD / "video" / "1020_IriunWebcam_before.avi"},
    "Thermal sample (12 s, drinking a cold drink)": {
        "thermal": SESSIONS / "thermal-s01.frames.bin", "thermal_meta": SESSIONS / "thermal-s01.json"},
}

PHQ = ["Not at all", "Several days", "More than half the days", "Nearly every day"]
COLORS = {"URGENT": "#c62828", "SEE_DOCTOR_SOON": "#ef6c00", "SELF_CARE": "#2e7d32", "RETAKE": "#546e7a",
          "REMEASURE": "#1565c0"}
LABELS = {"URGENT": "URGENT: get medical help now", "SEE_DOCTOR_SOON": "SEE A DOCTOR SOON",
          "SELF_CARE": "SELF-CARE & MONITOR", "RETAKE": "RETAKE THE MEASUREMENT",
          "REMEASURE": "REST 5 MINUTES, THEN RECORD AGAIN"}
NAMES = {"heart_rate": "Heart rate", "resp_rate": "Breathing rate", "temperature": "Temperature", "spo2": "SpO2",
         "sbp": "Systolic BP", "dbp": "Diastolic BP"}

st.set_page_config(page_title="Triage kiosk prototype", page_icon="🩺", layout="wide")
cfg = st.cache_resource(load_config)()
RED_FLAGS = list(cfg["red_flags"]["urgent_items"])
CONTEXT = list(cfg["questionnaire"]["sections"]["context"]["items"])
S = st.session_state
TMP = Path(S.setdefault("tmp", tempfile.mkdtemp(prefix="triage_kiosk_")))


def label(item):
    return item.replace("_", " ").capitalize()


def question(item):
    q = cfg["red_flags"]["items"].get(item, {}).get("question")
    return q or cfg["questionnaire"]["sections"]["context"]["items"].get(item, {}).get("question", label(item))


def save(upload, prefix):
    """Write an uploaded file to the session's temp folder (OpenCV and numpy need a path)."""
    if upload is None:
        return None
    p = TMP / f"{prefix}_{upload.name}"
    p.write_bytes(upload.getvalue())
    return p


def digest(paths):
    h = hashlib.sha1()
    for p in paths:
        if p:
            h.update(str(p).encode())
            h.update(Path(p).read_bytes() if Path(p).stat().st_size < 5e8 else b"")
    return h.hexdigest()


@st.cache_data(show_spinner=False, max_entries=8)
def analyse(content_key, video, thermal, thermal_fps, thermal_meta, contact, kind, contact_fs):
    """content_key (file hashes) is part of the cache key, so a re-uploaded file with the same name is re-measured."""
    return measure_recordings(video=video, thermal=thermal, thermal_fps=thermal_fps, thermal_meta=thermal_meta,
                              contact=contact, contact_kind=kind, contact_fs=contact_fs,
                              min_quality=cfg["ranges"]["min_quality"])


def recordings_form(prefix, default_sample=None):
    """Sample picker + uploaders. Returns the analyse() arguments, or None when nothing is given."""
    choice = st.radio("Recordings", ["Use a bundled real sample", "Upload my own recordings"], horizontal=True,
                      key=f"{prefix}_mode")
    if choice.startswith("Use"):
        names = [n for n, f in SAMPLES.items() if all(Path(p).exists() for p in f.values())]
        if not names:
            st.error("The bundled samples are not on this machine (data/public/mcd_rppg).")
            return None
        name = st.selectbox("Sample", names, key=f"{prefix}_sample",
                            index=names.index(default_sample) if default_sample in names else 0)
        f = SAMPLES[name]
        st.caption("Files: " + ", ".join(Path(p).name for p in f.values()) +
                   ". MCD-rPPG (Egorov et al., ACM MM 2025, CC-BY-4.0).")
        return dict(video=f.get("video"), thermal=f.get("thermal"), thermal_fps=None,
                    thermal_meta=f.get("thermal_meta"), contact=f.get("contact"), kind="ecg", contact_fs=None)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("**Face video** → heart rate (rPPG)")
        v = save(st.file_uploader("mp4 / avi / mov / mkv", ["mp4", "avi", "mov", "mkv"], key=f"{prefix}_v"), "video")
    with c2:
        st.write("**Thermal recording** → temperature, breathing rate")
        t = save(st.file_uploader(".npy (frames × height × width, °C) or .frames.bin", ["npy", "bin"],
                                  key=f"{prefix}_t"), "thermal")
        tm = save(st.file_uploader("its .json (for .frames.bin)", ["json"], key=f"{prefix}_tm"), "thermalmeta")
        tfps = st.number_input("thermal frame rate (for .npy)", 1.0, 120.0, 8.0, key=f"{prefix}_tfps")
    with c3:
        st.write("**ECG / finger-PPG file** → heart rate")
        c = save(st.file_uploader("csv (time column or rate) or MCD .json", ["csv", "json", "txt"],
                                  key=f"{prefix}_c"), "contact")
        kind = st.radio("signal type", ["ecg", "ppg"], horizontal=True, key=f"{prefix}_kind")
        cfs = st.number_input("sampling rate in Hz (0 = read from the file)", 0.0, 5000.0, 0.0, key=f"{prefix}_cfs")
    if not (v or t or c):
        return None
    if t and t.suffix == ".bin" and not tm:
        st.warning("A .frames.bin needs its .json.")
        return None
    return dict(video=v, thermal=t, thermal_fps=tfps if t and t.suffix == ".npy" else None, thermal_meta=tm,
                contact=c, kind=kind, contact_fs=cfs or None)


def run_analysis(args):
    key = digest([args["video"], args["thermal"], args["thermal_meta"], args["contact"]]) + json.dumps(
        {k: v for k, v in args.items() if k in ("thermal_fps", "kind", "contact_fs")})
    with st.spinner("Measuring vitals from the recordings… (a 3-minute video takes about a minute)"):
        return analyse(key, *[str(args[k]) if args[k] else None for k in ("video", "thermal")],
                       args["thermal_fps"], str(args["thermal_meta"]) if args["thermal_meta"] else None,
                       str(args["contact"]) if args["contact"] else None, args["kind"], args["contact_fs"])


def show_measurements(ms, flags, diag):
    rows = [{"measure": NAMES.get(m["name"], m["name"]), "value": m["value"], "unit": m["unit"],
             "readings": ", ".join(map(str, m.get("repeat_values", [m["value"]]))), "quality": m["quality"],
             "source": m["source"]} for m in ms]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if "heart_rate_sources" in diag:
        h = diag["heart_rate_sources"]
        st.caption(f"Heart rate used: **{h['used']}**; the {h['other']} estimate differs by {h['difference_bpm']} bpm.")
    if "face_not_found" in flags:
        st.error("No face was found in the video.")
    tabs = st.tabs([n for n, k in (("Face video", "video"), ("Thermal", "thermal"), ("ECG / PPG", "contact"))
                    if k in diag] or ["Details"])
    i = 0
    if "video" in diag:
        d = diag["video"]
        with tabs[i]:
            a, b = st.columns([1, 2])
            if d.get("preview"):
                img, (x, y, w, h) = d["preview"]
                img = img.copy()
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.rectangle(img, (x + int(.2 * w), y + int(.25 * h)), (x + int(.8 * w), y + int(.85 * h)),
                              (255, 200, 0), 2)
                a.image(img, caption="face (green) and skin area used (yellow)", width="stretch")
            if d.get("signal") is not None:
                sig = np.asarray(d["signal"])[-int(20 * d["fps"]):]
                b.write("Pulse wave from the face (POS), last 20 s")
                b.line_chart(pd.DataFrame({"pulse": sig}, index=np.round(np.arange(len(sig)) / d["fps"], 2)),
                             height=180)
            if d.get("halves"):
                b.dataframe(pd.DataFrame(d["halves"]).rename(columns={"hr_pos": "HR POS", "hr_chrom": "HR CHROM",
                                                                       "snr_db": "SNR dB"}), hide_index=True)
            st.caption(f"{d['duration_s']} s at {d['fps']:.0f} fps; face in {d['face_share']:.0%} of frames; "
                       f"quality parts {d.get('quality_parts')}; codec check {d.get('codec')}. {d.get('error', '')}")
        i += 1
    if "thermal" in diag:
        d = diag["thermal"]
        with tabs[i]:
            a, b = st.columns([1, 2])
            fr = np.asarray(d["preview"])
            img = cv2.applyColorMap(cv2.normalize(fr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
                                    cv2.COLORMAP_INFERNO)
            a.image(img[:, :, ::-1], caption=f"middle frame ({fr.min():.1f} to {fr.max():.1f} °C)", width="stretch")
            if d["temperature"].get("series") is not None:
                s = np.asarray(d["temperature"]["series"])
                b.write("Hottest-face-pixel temperature over time (°C)")
                b.line_chart(pd.DataFrame({"temperature": s}, index=np.round(np.arange(len(s)) / d["fps"], 2)),
                             height=180)
            st.caption(f"{d['duration_s']} s at {d['fps']:.0f} fps. Calibration offset "
                       f"{d['temperature'].get('offset_c')} °C (placeholder). Breathing: "
                       f"{d['resp'].get('error') or 'measured from ' + str(d['resp'].get('blocks_used')) + ' blocks'}")
        i += 1
    if "contact" in diag:
        d = diag["contact"]
        with tabs[i]:
            x = np.asarray(d["preview"])
            st.write(f"{d['kind'].upper()} ({d['signal_used']}), first 10 s")
            st.line_chart(pd.DataFrame({d["kind"]: x}, index=np.round(np.arange(len(x)) / d["preview_fs"], 3)),
                          height=180)
            st.caption(f"{d.get('beats', 0)} beats in {d.get('duration_s')} s; regular share "
                       f"{d.get('regular_share')}. {d.get('error', '')}")


def build_record(ms, flags):
    rec = new_record("kiosk-ui", cfg, code="ui")
    for m in ms:
        add_measurement(rec, m["name"], m["value"], m["unit"], m["quality"], m["source"], m.get("error_margin"),
                        m.get("repeat_values"))
    add_answer(rec, "age", int(S["age"]))
    add_answer(rec, "pregnant", S["pregnant"])
    for item in RED_FLAGS + ["self_harm"] + CONTEXT:
        add_answer(rec, item, "yes" if S.get(f"a_{item}") else "no")
    if S.get("days", 0) > 0:
        add_answer(rec, "has_symptom", "yes")
        add_answer(rec, "symptom_duration_days", int(S["days"]))
    add_score(rec, "PHQ2", PHQ.index(S["phq2_1"]) + PHQ.index(S["phq2_2"]))
    add_score(rec, "GAD2", PHQ.index(S["gad2_1"]) + PHQ.index(S["gad2_2"]))
    rec["flags"] += flags
    return rec


def device_inputs():
    with st.expander("Optional: BP cuff / clip oximeter readings (typed from the device display)"):
        out = {}
        for k, unit in (("spo2", "%"), ("sbp", "mmHg"), ("dbp", "mmHg")):
            a, b, c = st.columns([1.3, 1, 1])
            if a.checkbox(NAMES[k], key=f"use_{k}"):
                out[k] = (unit, [b.number_input("reading 1", 0.0, 300.0, {"spo2": 98.0, "sbp": 120.0,
                                                                          "dbp": 80.0}[k], key=f"{k}_1"),
                                 c.number_input("reading 2", 0.0, 300.0, {"spo2": 98.0, "sbp": 120.0,
                                                                          "dbp": 80.0}[k], key=f"{k}_2")])
        return out


def show_card(rec):
    ch = {s["step"]: s for s in rec["chain"]}
    adv, rule = ch["advice"], ch["rule"]
    ids = by_id(rec)
    st.markdown(f"<div style='background:{COLORS[adv['level']]};color:white;padding:18px 22px;border-radius:12px;"
                f"font-size:1.5rem;font-weight:700'>{LABELS[adv['level']]}</div>", unsafe_allow_html=True)
    st.markdown(f"#### {adv['text'] if adv['level'] != 'REMEASURE' else 'Please rest quietly for 5 minutes, then record again below.'}")
    st.write(f"**Why:** {rule['reason']}")
    if rule["refs"]:
        cited = []
        for r in rule["refs"]:
            x = ids[r]
            cited.append(f"`{r}` {NAMES.get(x['name'], x['name'])}: {x.get('repeat_values', x['value'])} {x['unit']}"
                         f" (from {x['source']})" if "unit" in x else
                         f"`{r}` {label(x.get('item', x.get('name')))} = {x.get('answer', x.get('value'))}")
        st.write("**Based on:** " + "; ".join(cited))
    if adv["contacts"]:
        st.error("**Call:** " + " · ".join(f"{c['name']}: **{c['number']}**" for c in adv["contacts"])
                 + ("" if adv["contacts_verified"] else "  _(numbers not yet verified by the team)_"))
    rows = [{"measure": NAMES.get(i["name"], i["name"]), "readings": ", ".join(map(str, i["readings"])) or "-",
             "unit": i["unit"], "normal range": "" if "normal" not in i else
             f"{i['normal'][0]} to {i['normal'][1] if i['normal'][1] is not None else '…'}",
             "error margin": i["margin"], "quality": i["quality"], "status": i["status"]}
            for i in ch["interpretation"]["items"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    ctx = [c for c in ch["context"]["items"] if c.get("answer") == "yes" or c.get("note")]
    c1.write("**Context answers**")
    c1.write("\n".join(f"- {label(c['item'])}: {c.get('answer') or c.get('note')}"
                       + (f" ({c['effect']})" if c.get("effect") else "") for c in ctx) or "none")
    c2.write("**Uncertainty**")
    c2.write("\n".join(f"- {u['text']}" + (f": {', '.join(u['names'])}" if u.get("names") else "")
                       for u in ch["uncertainty"]["items"]) or "none")
    also = [m["rule_id"] for m in rec["decision"]["also_matched"]]
    st.caption(f"Rule {rule['rule_id']} set the level" + (f"; also matched: {', '.join(also)}" if also else "")
               + f". {adv['disclaimer']}")


def show_explanation(rec):
    """Plain-language explanation (LLM, verified; else the template) and the follow-up chat."""
    if "card" not in S:
        with st.spinner("Writing the explanation (local model)…"):
            S["card"], S["card_log"] = explain(rec, cfg)
    card, log = S["card"], S["card_log"]
    st.markdown("#### In plain words")
    st.write(card["summary"])
    st.write("\n".join(f"- {r}" for r in card["reasons"]))
    if card["uncertainty"]:
        st.write(f"**What is uncertain:** {card['uncertainty']}")
    if card["next_step"]:
        st.write(f"**Next step:** {card['next_step']}")
    st.caption(f"Text: {'local LLM, checked by the verifier' if log['source'].startswith('llm') else 'fixed template'}"
               f" ({log['seconds']} s). The level, advice, contacts and disclaimer are set by the rules, not the LLM.")
    if rec["decision"]["level"] == "REMEASURE":
        return
    st.markdown("#### Questions about your result")
    knowledge = st.cache_resource(load_knowledge)(demo=True)
    for q, a in S.setdefault("chat", []):
        st.chat_message("user").write(q)
        st.chat_message("assistant").write(a)
    q = st.chat_input("Ask about your result (not about medicines or illnesses)")
    if q:
        with st.spinner("…"):
            res = followup_answer(q, rec, cfg, knowledge)
        S["chat"].append((q, res["answer"]))
        st.rerun()


# ---------------------------------------------------------------- page

st.title("🩺 Guided triage: kiosk prototype")
if not DEMO and approval_problems(cfg):
    st.error("This kiosk cannot run user sessions yet: the rules, ranges, wording or contact numbers are still DRAFTS "
             f"({len(approval_problems(cfg))} clinician sign-off items open). For demonstrations with synthetic or "
             "sample data, start it in demo mode: `streamlit run src/triage/kiosk_app.py -- --demo`.")
    st.write("\n".join(f"- {p}" for p in approval_problems(cfg)))
    st.stop()
st.warning(("DEMO MODE. " if DEMO else "") + "Research prototype. Rules, ranges, wording and measurement calibration are **DRAFTS** that no clinician "
           f"has reviewed yet ({len(approval_problems(cfg))} sign-off items open). This check is informational and "
           "is not a medical diagnosis.")
run_tab, rules_tab, bench_tab = st.tabs(["Run a check", "Rule table", "Benchmark results"])

with run_tab:
    st.subheader("1 · Recordings")
    args = recordings_form("r1")
    devices = device_inputs()
    if st.button("Measure vitals from the recordings", type="primary", disabled=args is None):
        try:
            ms, flags, diag = run_analysis(args)
            S["meas"] = (ms, flags, diag)
            S.pop("rec", None)
        except Exception as e:                         # unreadable or unsupported file: show it, keep the page alive
            st.error(f"Could not read the recording: {e}")
    if "meas" in S:
        ms, flags, diag = S["meas"]
        from triage.measure.devices import device_reading
        ms = [m for m in ms if m["source"] != "device"] + [device_reading(k, r, u) for k, (u, r) in devices.items()]
        show_measurements(ms, flags, diag)

        st.subheader("2 · Questions")
        st.checkbox(question("consent"), key="consent")
        if not S.get("consent"):
            st.info("The check continues only with your consent. Nothing is stored without it.")
            st.stop()
        a1, a2 = st.columns(2)
        a1.number_input(question("age"), 0, 120, 35, key="age")
        a2.radio(question("pregnant"), ["no", "yes", "not sure"], horizontal=True, key="pregnant")
        left, right = st.columns(2)
        with left:
            st.write("**Warning signs**")
            for item in RED_FLAGS:
                st.toggle(question(item), key=f"a_{item}")
            st.write("**Context**")
            for item in CONTEXT:
                st.toggle(question(item), key=f"a_{item}")
            st.number_input("Days you have had a health problem that bothers you (0 = none)", 0, 365, key="days")
        with right:
            st.write("**Over the last 2 weeks, how often have you been bothered by…**")
            for key, text in (("phq2_1", "Little interest or pleasure in doing things"),
                              ("phq2_2", "Feeling down, depressed, or hopeless"),
                              ("gad2_1", "Feeling nervous, anxious, or on edge"),
                              ("gad2_2", "Not being able to stop or control worrying")):
                S.setdefault(key, PHQ[0])
                st.select_slider(text, PHQ, key=key)
            st.toggle(question("self_harm"), key="a_self_harm")

        st.subheader("3 · Result")
        if st.button("Run check", type="primary", width="stretch"):
            S["rec"] = apply(build_record(ms, flags), cfg)
            S.pop("card", None)
            S["chat"] = []
        if "rec" in S:
            show_card(S["rec"])
            show_explanation(S["rec"])
            if S["rec"]["decision"]["level"] == "REMEASURE":
                st.info("Second recording after 5 minutes of rest:")
                args2 = recordings_form("r2")
                if st.button("Measure again and decide", type="primary", disabled=args2 is None):
                    ms2, flags2, diag2 = run_analysis(args2)
                    rec = copy.deepcopy(S["rec"])
                    new = {m["name"]: m for m in ms2}
                    for m in rec["measurements"]:
                        n = new.get(m["name"])
                        if n and n["value"] is not None:
                            m.update(value=n["value"], quality=n["quality"], source=n["source"],
                                     repeat_values=n.get("repeat_values", [n["value"]]),
                                     n_readings=len(n.get("repeat_values", [n["value"]])))
                    rec["flags"] = sorted(set(rec["flags"] + flags2 + ["remeasured"]))
                    rec["decision"] = rec["chain"] = None
                    S["rec"] = apply(rec, cfg)
                    S.pop("card", None)
                    S["chat"] = []
                    st.rerun()
            with st.expander("Evidence record and reasoning chain (JSON)"):
                st.json(json.loads(json.dumps(S["rec"])))

with rules_tab:
    st.write(f"Rules **{cfg['rules']['version']}** ({cfg['rules']['status']}). The first matching rule sets the "
             "level.")
    st.dataframe(pd.DataFrame(rule_table(cfg)), hide_index=True, width="stretch")
    with st.expander("What still blocks user tests (clinician sign-off)"):
        st.write("\n".join(f"- {p}" for p in approval_problems(cfg)))

with bench_tab:
    for name in ("REPORT.md", "COMPARISON.md"):
        p = ROOT / "results" / "triage" / name
        if p.exists():
            st.markdown(p.read_text(encoding="utf-8"))
            st.divider()
        else:
            st.info(f"{name} not found yet: run `python -m triage.bench.run_bench` and "
                    "`python -m triage.bench.compare_published` from reasoning_model/src.")
