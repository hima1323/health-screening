"""Export ADABase subjects as study sessions for the web app (server/data/sessions/adabase-<id>.json).

Per subject: the agent + fusion model's out-of-fold P(high load) per window on the n-back task, the per-agent
log-odds contributions, and the LLM's verified explanations (results/explanations_fusion/). The fields follow
server/models/StudySession.js, so `npm run sessions` loads them and the existing analysis page renders them.
Usage: python src/export_sessions.py [--subjects 0004-BDCD 0000-ACAA 0027-YMAD]
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "server" / "data" / "sessions"
STEP = 15  # s between window starts (30 s windows, 50% overlap)
AGENTS = {"au": "Face (action units)", "eye": "Eye tracker", "ecg": "ECG", "ppg": "Pulse (PPG)",
          "eda": "Skin conductance", "rsp": "Breathing", "emg": "Muscle (EMG)", "skt": "Skin temperature"}


# resting vitals with a clinical normal range: (column, label, unit, normal text, test)
VITALS = [("ecg_hr", "Heart rate at rest", "bpm", "50–100", lambda v: 50 <= v <= 100),
          ("ecg_rmssd", "Heart-rate variability", "ms", "20 or more", lambda v: v >= 20),
          ("rsp_rate", "Breathing rate at rest", "breaths/min", "12–20", lambda v: 12 <= v <= 20)]


def summary(sid, matched, rounds):
    """What the patient reads: resting vitals (5-min rest before the n-back task) against normal ranges, plus how
    their body answered the harder rounds. Normal/not is decided by the vitals only; effort is not a health measure."""
    feats = pd.read_parquet(ROOT / "data" / "features" / f"{sid}.parquet")
    rest = feats[(feats.study == "n-back") & (feats.phase == "baseline") & (feats.level == 1)]
    readings = [{"label": label, "value": round(float(rest[col].mean()), 1), "unit": unit, "normal": normal,
                 "ok": bool(ok(rest[col].mean()))}
                for col, label, unit, normal, ok in VITALS if rest[col].notna().any()]
    off = [r["label"].replace(" at rest", "").lower() for r in readings if not r["ok"]]
    readings.append({"label": "Body's response to harder tasks", "value": matched, "unit": f"of {rounds} rounds",
                     "normal": "most rounds", "ok": matched * 2 > rounds,
                     "note": "How clearly your body reacted to mental effort — not a health measure"})
    text = (f"Your {' and '.join(off)} {'was' if len(off) == 1 else 'were'} outside the normal range at rest."
            if off else "All your resting readings were in the healthy range.")
    advice = ({"level": "routine", "answer": "Maybe",
               "text": f"Mention your {' and '.join(off)} at your next check-up — one recording is not enough to be sure."}
              if off else {"level": "ok", "answer": "No", "text": "Your resting readings are in the healthy range."})
    return {"status": "abnormal" if off else "normal", "text": text, "readings": readings}, advice


def phase_name(n, dual):
    return f"{n}-back{' dual' if dual else ''}"


def tidy(text):
    """Display only: 3 significant figures ('-0.01706 F/s' → '-0.0171 F/s') and no trailing ', indicating high
    activity' — the group heading already says which way it points. The verifier already checked the originals."""
    text = re.sub(r",?\s+(indicating|suggesting)\b[^.]*\.?$", "", text.strip()).rstrip(".") + "."
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m[0]):.3g}", text)


def by_push(items, w):
    """Strongest agent first, by |log-odds contribution| in this window."""
    return sorted(items, key=lambda i: -abs(np.nan_to_num(w.get(f"contrib_{i.get('modality')}", 0))))


def item(i, w):
    return {"label": AGENTS.get(i.get("modality"), i.get("modality", "")), "text": tidy(i["statement"])}


def steps(sid, windows):
    """One reasoning step per n-back level: the first verified explanation in it, else the first one."""
    path = ROOT / "results" / "explanations_fusion" / f"{sid}.jsonl"
    exps = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    out = []
    for level, group in pd.DataFrame(exps).groupby("level", sort=True) if exps else []:
        e = max(group.to_dict("records"), key=lambda x: x["verified"])
        w = windows[(windows.level == level) & (windows.win_start == e["win_start"])].iloc[0]
        o = e["output"]
        other = "high" if o["conclusion"] == "low" else "low"
        step = {"look": f"{phase_name(w.nback_n, w.dual)} · {int(w.win_start)}–{int(w.win_start) + 30} s"}
        if not e["verified"]:
            step["found"] = "No explanation shown: the explainer quoted numbers that aren't in the data, twice."
        elif o["abstain"]:
            step["found"] = "No explanation shown: confidence was below 60% or the signals were poor."
        else:
            step["groups"] = [{"heading": f"Points to {side} load", "items": [item(i, w) for i in by_push(items, w)]}
                              for side, items in ((o["conclusion"], o["evidence"]), (other, o["conflicts"])) if items]
        truth = "high" if w.y else "low"
        out.append({**step,
                    "so": f"Model says {o['conclusion']} load ({o['confidence']:.0%} confident); "
                          f"the task was {truth} load{'' if o['conclusion'] == truth else ' — a miss'}."})
    return out


def session(sid, df):
    d = df[df.subject == sid].sort_values(["level", "win_start"]).reset_index(drop=True)
    pred = (d.prob >= 0.5).astype(int)
    auroc, bacc = roc_auc_score(d.y, d.prob), balanced_accuracy_score(d.y, pred)
    phases, metrics, findings, start = [], [], [], 0
    for (level, n, dual), g in d.groupby(["level", "nback_n", "dual"], sort=True):
        name, called = phase_name(n, dual), int((g.prob >= 0.5).sum())
        phases.append({"name": name, "startS": start, "endS": start + len(g) * STEP, "discontinuous": start > 0,
                       "note": f"{'Dual' if dual else 'Single'} task, {'high' if g.y.iloc[0] else 'low'} load"})
        metrics.append({"phase": name, "values": {"meanProb": round(float(g.prob.mean()), 2),
                                                  "calledHigh": round(100 * called / len(g))}})
        right = called if g.y.iloc[0] else len(g) - called
        findings.append({"label": f"{name} · {'hard' if g.y.iloc[0] else 'easy'} round",
                         "tone": "ok" if right * 2 > len(g) else "warn",
                         "detail": f"Read as high effort {called} of {len(g)} times — "
                                   f"{'as expected' if right * 2 > len(g) else 'not what the task asked for'}"})
        start += len(g) * STEP
    avail = [m for m in AGENTS if d[f"agent_{m}"].notna().any()]
    tracks = [{"key": "p-high", "group": "load", "label": "Fused P(high load)", "fs": 1 / STEP,
               "values": d.prob.round(3).tolist()}]
    tracks += [{"key": f"agent-{m}", "group": "load", "label": AGENTS[m], "fs": 1 / STEP,
                "values": d[f"agent_{m}"].round(3).tolist()} for m in ("au", "eye") if d[f"agent_{m}"].notna().all()]
    tracks.append({"key": "nback", "group": "task", "label": "n-back level", "fs": 1 / STEP,
                   "values": d.nback_n.astype(int).tolist()})
    verdict = "Good" if auroc >= 0.8 else "Fair" if auroc >= 0.65 else "Poor"
    patient_summary, advice = summary(sid, sum(f["tone"] == "ok" for f in findings), len(findings))
    return {
        "id": f"adabase-{sid.split('-')[0]}",
        "source": {"dataset": "ADABase", "kind": "public", "url": "https://doi.org/10.3390/s23010340",
                   "note": "ADABase n-back recordings (Oppelt et al., 2023). Predictions are out-of-fold: the model "
                           "never saw this subject during training."},
        "subject": {"id": sid},
        "label": "Cognitive load · n-back",
        "durationS": start,
        "modalities": [{"key": m, "label": AGENTS[m], "detail": "Recorded"} for m in avail],
        "phases": phases,
        "tracks": tracks,
        "metricDefs": [{"key": "meanProb", "label": "Mean P(high load)", "digits": 2},
                       {"key": "calledHigh", "label": "Windows called high", "unit": "%", "digits": 0}],
        "metrics": metrics,
        "quality": {"status": "good" if len(avail) == len(AGENTS) else "fair",
                    "message": f"{len(avail)} of {len(AGENTS)} modality agents had data. Time axis is window "
                               f"time: one point per 30 s window, every {STEP} s."},
        "fusion": {
            "title": "Agents + fusion",
            "method": "One LightGBM agent per modality, combined by a logistic regression with non-negative "
                      "weights · trained on the other 29 subjects",
            "score": int((pred == d.y).sum()), "scoreMax": len(d), "band": "windows classified correctly",
            "verdict": verdict,
            "stats": [{"label": "AUROC", "value": f"{auroc:.2f}", "hint": "0.5 is chance, 1.0 is perfect"},
                      {"label": "Balanced accuracy", "value": f"{bacc:.0%}", "hint": "Mean of low and high recall"}],
            "parts": [{"key": m, "label": AGENTS[m], "points": None,
                       "reading": f"average push {d[f'contrib_{m}'].abs().mean():.2f} log-odds · "
                                  f"available in {d[f'agent_{m}'].notna().mean():.0%} of windows"}
                      for m in sorted(avail, key=lambda m: -d[f"contrib_{m}"].abs().mean())],
            "note": "The fused log-odds are the sum of the agents' contributions; the larger an agent's push, "
                    "the more it decides the label. Positive pushes toward high load.",
        },
        "summary": patient_summary,
        "assessment": {
            "condition": f"Your effort readings matched the task in {sum(f['tone'] == 'ok' for f in findings)} "
                         f"of {len(findings)} rounds",
            "findings": findings,
            "advice": advice,
            "disclaimer": "Research prototype trained on 30 ADABase subjects; not validated for screening.",
        },
        "reasoning": {
            # plain words for the patient; AUROC and the explained windows are on the doctor's page
            "conclusion": {"Good": "Your body clearly showed when the memory task got harder.",
                           "Fair": "Your body partly showed when the memory task got harder.",
                           "Poor": "Your body's signals did not clearly show when the task got harder, so this "
                                   "reading is unreliable for you."}[verdict]
                          + " This measures mental effort, not health.",
            "steps": steps(sid, d),
        },
    }


if __name__ == "__main__":
    assert tidy("Muscle is 0.01298 a.u., indicating high activity.") == "Muscle is 0.013 a.u."
    assert tidy("AU14 is high, contributing 2.301 to the fusion model.") == "AU14 is high, contributing 2.3 to the fusion model."
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", nargs="+", default=["0004-BDCD", "0000-ACAA", "0027-YMAD"])  # best, median, worst
    df = pd.read_parquet(ROOT / "results" / "oof_fusion.parquet")
    for sid in ap.parse_args().subjects:
        s = session(sid, df)
        assert not np.isnan([v for t in s["tracks"] for v in t["values"]]).any(), sid
        (OUT / f"{s['id']}.json").write_text(json.dumps(s, indent=1, allow_nan=False))
        print(s["id"], s["fusion"]["stats"][0]["value"], len(s["reasoning"]["steps"]), "steps")
