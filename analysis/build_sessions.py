"""
Build the study sessions the timeline shows, one JSON file per session.

Only results our four modalities can produce are kept — rPPG, thermal, ECG
and EMG. Contact PPG, clinic instruments and the drive's respiration and
skin-conductance channels are left out.

  MCD-rPPG   camera pulse from each sitting's face video (POS, checked
             against CHROM), at rest and after exercise
  drivedb    Hans's ECG session with the EMG recorded alongside it
  thermal    Hans's thermal session: four facial ROIs through a cold drink

Every stage is timed, so the pipeline the dashboard draws is the one that ran.

    python analysis/build_sessions.py
"""
import csv
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RPPG = os.path.join(ROOT, "rppg1")
sys.path[:0] = [os.path.join(RPPG, "webapp")]
import vitals  # noqa: E402

OUT = os.path.join(ROOT, "server", "data", "sessions")
CACHE = os.path.join(ROOT, "analysis", "sources")
MCD = os.path.join(RPPG, "data")
HANS = "repos/h4444n55555/Multimodal-Analysis-Dashboards/contents/website/public/data"

FPS = 30.0

# A camera reading is trusted only when its SNR is at least 0 dB and POS and
# CHROM agree within 5 bpm. Calibrated offline against MCD's contact PPG:
# the gate keeps 12 of 35 sittings at 11.4 bpm mean error, but 3 kept
# readings are still off by more than 15 bpm — so a camera reading alone
# never sends anyone to a doctor, it asks for a rescan.
MIN_SNR_DB = 0.0
MAX_METHOD_GAP = 5.0


def r(x, d=2):
    """Round for JSON; NaN and None both become null."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), d)


def series(values, d=3):
    return [r(v, d) for v in values]


def downsample(values, n):
    """Mean-pool a long series to about n points, keeping its shape."""
    values = np.asarray(values, dtype=np.float64)
    if values.size <= n:
        return values
    edges = np.linspace(0, values.size, n + 1).astype(int)
    return np.array([values[a:b].mean() for a, b in zip(edges[:-1], edges[1:])])


class Stopwatch:
    """Times named stages so the pipeline trace reports what actually ran."""

    def __init__(self):
        self.ms = {}

    def __call__(self, name):
        watch = self

        class _Lap:
            def __enter__(self):
                self.t = time.perf_counter()

            def __exit__(self, *_):
                watch.ms[name] = watch.ms.get(name, 0) + (time.perf_counter() - self.t) * 1000

        return _Lap()


# ── Assessment ────────────────────────────────────────────────────────────
# A screening aid, not a diagnosis. Heart rate uses the standard adult
# resting range; HRV uses the usual short-term RMSSD floor.

RANK = {"ok": 0, "rescan": 1, "routine": 1, "soon": 2, "urgent": 3}
TONE = {"ok": "ok", "rescan": "warn", "routine": "warn", "soon": "bad", "urgent": "bad"}


def hr_category(hr):
    if hr >= 130:
        return "Very fast resting heart rate", "urgent"
    if hr > 100:
        return "Fast resting heart rate (tachycardia)", "soon"
    if hr < 40:
        return "Very slow resting heart rate", "urgent"
    if hr < 50:
        return "Slow resting heart rate (bradycardia)", "soon"
    return "Normal resting heart rate", "ok"


def advice(level, condition):
    return {
        "ok": {"level": "ok", "answer": "No",
               "text": "No need to contact a doctor — the resting readings are within normal ranges."},
        "rescan": {"level": "rescan", "answer": "Rescan first",
                   "text": condition},
        "routine": {"level": "routine", "answer": "At your next check-up",
                    "text": f"Not urgent. Mention {condition.lower()} to your doctor at your next routine visit."},
        "soon": {"level": "soon", "answer": "Yes, within a few days",
                 "text": f"Book an appointment with a doctor about {condition.lower()}."},
        "urgent": {"level": "urgent", "answer": "Yes, today",
                   "text": f"Seek medical care today — {condition.lower()}."},
    }[level]


def summarise(findings):
    """The condition line and the doctor advice follow from the worst finding."""
    flagged = [f for f in findings if f.get("_level", "ok") != "ok"]
    worst = max((f["_level"] for f in findings if "_level" in f), key=RANK.get, default="ok")
    condition = "; ".join(f["label"] for f in flagged) if flagged else "No abnormal findings at rest"
    for f in findings:
        f.pop("_level", None)
    return condition, advice(worst, condition)


def finding(label, detail, level):
    return {"label": label, "detail": detail, "tone": TONE[level], "_level": level}


DISCLAIMER = ("Screening aid, not a diagnosis. Heart rate uses the standard adult resting range (50–100 bpm); "
              "a camera reading outside it asks for a rescan before any doctor visit.")


# ── Camera: MCD-rPPG ──────────────────────────────────────────────────────

def skin_rgb(frames):
    """Mean skin colour per frame — the trace both rPPG methods start from."""
    return frames.reshape(len(frames), -1, 3).mean(1).astype(np.float64)


def pos(rgb):
    """Plane-Orthogonal-to-Skin, Wang et al., IEEE TBME 2017."""
    L = int(1.6 * FPS)
    out = np.zeros(len(rgb))
    project = np.array([[0, 1, -1], [-2, 1, 1]])
    for t in range(len(rgb) - L + 1):
        s = (rgb[t:t + L] / rgb[t:t + L].mean(0)) @ project.T
        h = s[:, 0] + s[:, 1] * (s[:, 0].std() / (s[:, 1].std() + 1e-9))
        out[t:t + L] += h - h.mean()
    return out


def chrom(rgb):
    """Chrominance method, de Haan & Jeanne, IEEE TBME 2013 — the second opinion."""
    L = int(1.6 * FPS)
    out = np.zeros(len(rgb))
    window = np.hanning(L)
    for t in range(0, len(rgb) - L + 1, L // 2):
        c = rgb[t:t + L] / rgb[t:t + L].mean(0)
        x = vitals.bandpass(3 * c[:, 0] - 2 * c[:, 1], FPS, *vitals.HR_BAND_HZ)
        y = vitals.bandpass(1.5 * c[:, 0] + c[:, 1] - 1.5 * c[:, 2], FPS, *vitals.HR_BAND_HZ)
        if x is None or y is None:
            continue
        s = x - (x.std() / (y.std() + 1e-9)) * y
        out[t:t + L] += (s - s.mean()) * window
    return out


def z(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / (x.std() + 1e-8)


def read_db():
    rows = {}
    with open(os.path.join(MCD, "raw_mcd", "db.csv")) as f:
        for row in csv.DictReader(f):
            if row["camera"] == "FullHDwebcam":
                rows[(row["patient_id"], row["step"])] = row
    return rows


def recorded_on(pid, step):
    try:
        with open(os.path.join(MCD, "raw_mcd", "meta", f"{pid}_FullHDwebcam_{step}.txt")) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
    except OSError:
        pass
    return None


def build_mcd():
    db = read_db()
    processed = os.path.join(MCD, "processed_mcd")
    by_subject = {}
    for name in sorted(os.listdir(processed)):
        pid, _, step = name.split("_")
        by_subject.setdefault(pid, {})[step] = os.path.join(processed, name)

    sessions = []
    for pid, steps in sorted(by_subject.items()):
        watch = Stopwatch()
        phases, track, metrics, trust = [], [], [], []
        order = [s for s in ("before", "after") if s in steps]

        for i, step in enumerate(order):
            with watch("load"):
                rgb = skin_rgb(np.load(os.path.join(steps[step], "frames.npy")))
            with watch("pos"):
                wave = pos(rgb)
            with watch("chrom"):
                second = chrom(rgb)
            with watch("estimate"):
                hr = vitals.estimate_hr(wave, FPS)
                hr2 = vitals.estimate_hr(second, FPS)
                snr = vitals.signal_quality_db(wave, FPS)
                gap = abs(hr - hr2)
                trusted = snr >= MIN_SNR_DB and gap <= MAX_METHOD_GAP

            start = i * len(wave) / FPS
            phases.append({"name": "Before" if step == "before" else "After",
                           "startS": r(start), "endS": r(start + len(wave) / FPS),
                           "discontinuous": i > 0,
                           "note": "Resting" if step == "before" else "After a short exercise bout"})
            track.extend(series(z(vitals.bandpass(wave, FPS, *vitals.HR_BAND_HZ))))
            trust.append(trusted)
            metrics.append({"phase": phases[-1]["name"], "values": {
                "cameraHr": r(hr, 1), "chromHr": r(hr2, 1), "methodGap": r(gap, 1), "snrDb": r(snr, 1)}})

        rest = metrics[0]["values"]
        with watch("assess"):
            findings = []
            if not trust[0]:
                why = (f"signal {rest['snrDb']} dB" if rest["snrDb"] < MIN_SNR_DB else
                       f"POS and CHROM disagree by {rest['methodGap']:.0f} bpm")
                findings.append(finding("No reliable reading",
                                        f"The camera signal was too weak to trust ({why}) — scan again, facing the camera "
                                        "in steady light", "rescan"))
            else:
                label, level = hr_category(rest["cameraHr"])
                if level == "ok":
                    findings.append(finding(label, f"{rest['cameraHr']:.0f} bpm at rest by camera (normal 50–100)", "ok"))
                else:
                    findings.append(finding(f"Possible {label[0].lower()}{label[1:]}",
                                            f"The camera read {rest['cameraHr']:.0f} bpm at rest (normal 50–100). "
                                            "Scan again to confirm; if it repeats, see a doctor", "rescan"))
            if len(metrics) > 1 and trust[0] and trust[1]:
                rise = metrics[1]["values"]["cameraHr"] - rest["cameraHr"]
                findings.append({"label": "Heart-rate response to exercise", "tone": "info",
                                 "detail": (f"+{rise:.0f} bpm after exercise — a normal rise" if rise >= 10 else
                                            f"{rise:+.0f} bpm after exercise — little change; the bout may have been light")})
            findings.append({"label": "Reading confidence", "tone": "info" if trust[0] else "warn",
                             "detail": f"Signal {rest['snrDb']} dB · POS and CHROM within {rest['methodGap']:.0f} bpm "
                                       f"({'consistent' if trust[0] else 'not consistent'})"})
            condition, advice_block = summarise(findings)

        row = db[(pid, order[0])]
        sessions.append({
            "id": f"mcd-{pid}",
            "source": {"dataset": "MCD-rPPG", "kind": "public",
                       "url": "https://huggingface.co/datasets/dypknu/mcd_rppg",
                       "note": "Face video of each sitting, at rest and after exercise. Only the camera is used."},
            "subject": {"id": pid, "age": int(float(row["age"])), "sex": row["sex"],
                        "bmi": r(float(row["bmi"]), 1)},
            "label": "Rest → after exercise" if len(order) == 2 else "Resting",
            "recordedOn": recorded_on(pid, order[0]),
            "durationS": r(len(order) * 10.0, 1),
            "modalities": [{"key": "rppg", "label": "rPPG", "detail": "FullHD webcam, 96 px face crop"}],
            "phases": phases,
            "tracks": [{"key": "rppg", "group": "pulse", "label": "Camera pulse (rPPG)", "unit": "z", "fs": FPS,
                        "values": track}],
            "metricDefs": [
                {"key": "cameraHr", "label": "Heart rate (POS)", "unit": "bpm", "digits": 1},
                {"key": "chromHr", "label": "Heart rate (CHROM)", "unit": "bpm", "digits": 1},
                {"key": "methodGap", "label": "Method gap", "unit": "bpm", "digits": 1, "lowerIsBetter": True},
                {"key": "snrDb", "label": "Signal quality", "unit": "dB", "digits": 1},
            ],
            "metrics": metrics,
            "quality": {"status": "good" if all(trust) else "fair" if trust[0] else "poor",
                        "message": ("The camera signal was consistent in every phase." if all(trust) else
                                    "The camera signal was consistent at rest." if trust[0] else
                                    "The resting camera signal was not consistent enough to trust.")},
            "fusion": {
                "title": "Single modality — camera only",
                "method": "Fusion needs two or more co-recorded modalities; this sitting has rPPG alone",
                "score": None, "scoreMax": None, "band": "Not applicable",
                "verdict": "Single channel",
                "stats": [{"label": "Trusted phases", "value": f"{sum(trust)} of {len(trust)}",
                           "hint": f"SNR ≥ {MIN_SNR_DB:.0f} dB and POS–CHROM within {MAX_METHOD_GAP:.0f} bpm"}],
                "parts": [{"key": m["phase"], "label": f"{m['phase']} — heart rate",
                           "reading": f"{m['values']['cameraHr']:.0f} bpm · {'trusted' if t else 'not trusted'}",
                           "points": None} for m, t in zip(metrics, trust)],
                "note": "Add a thermal or ECG channel recorded at the same sitting and this becomes a fused reading.",
            },
            "assessment": {"condition": condition, "findings": findings, "advice": advice_block,
                           "disclaimer": DISCLAIMER},
            "pipeline": [
                {"stage": "Face crop", "modality": "rppg", "status": "ok", "ms": None,
                 "detail": "Haar cascade on the first frame, 30% margin, resized to 96 px — done once in preprocessing"},
                {"stage": "Skin colour trace", "modality": "rppg", "status": "ok", "ms": r(watch.ms["load"], 0),
                 "detail": f"{len(order) * 300} frames reduced to their mean red, green and blue"},
                {"stage": "POS", "modality": "rppg", "status": "ok", "ms": r(watch.ms["pos"], 1),
                 "detail": "Colour projected onto the plane orthogonal to skin tone, 1.6 s windows — the pulse shown above"},
                {"stage": "CHROM", "modality": "rppg", "status": "ok", "ms": r(watch.ms["chrom"], 1),
                 "detail": "An independent chrominance method, used only to check POS"},
                {"stage": "HR and confidence", "modality": "rppg",
                 "status": "ok" if trust[0] else "degraded", "ms": r(watch.ms["estimate"], 1),
                 "detail": f"Spectral peak for heart rate; trusted when SNR ≥ {MIN_SNR_DB:.0f} dB and the methods "
                           f"agree within {MAX_METHOD_GAP:.0f} bpm"},
                {"stage": "PhysFormer", "modality": "rppg", "status": "skipped", "ms": None,
                 "detail": "Not used — the current checkpoint reads 49.5 bpm off on this data and needs retraining"},
                {"stage": "Assessment", "modality": "rppg", "status": "ok", "ms": r(watch.ms["assess"], 2),
                 "detail": "Resting heart rate against 50–100 bpm; outside it, or untrusted, asks for a rescan"},
            ],
        })
        readings = ", ".join(f"{m['values']['cameraHr']:.0f}{'' if t else '?'}" for m, t in zip(metrics, trust))
        print(f"  mcd-{pid}: {readings} bpm · {advice_block['answer']}")
    return sessions


def fetch(path):
    local = os.path.join(CACHE, path.replace("/", "_"))
    if not os.path.exists(local):
        os.makedirs(CACHE, exist_ok=True)
        # Hans's repo is private, so go through the authenticated GitHub CLI
        raw = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw", f"{HANS}/{path}"],
                             check=True, capture_output=True).stdout
        with open(local, "wb") as f:
            f.write(raw)
    with open(local) as f:
        return json.load(f)


def phase_mean(values, fs, phases):
    out = {}
    for p in phases:
        a, b = int(p["startS"] * fs), int(p["endS"] * fs)
        chunk = np.asarray(values[a:b], dtype=np.float64)
        out[p["name"]] = float(chunk.mean()) if chunk.size else None
    return out


# ── ECG + EMG: drivedb ────────────────────────────────────────────────────

def build_ecg():
    watch = Stopwatch()
    with watch("load"):
        d = fetch("ecg/S01.json")
    phases = [{"name": p["name"], "startS": r(p["startS"]), "endS": r(p["endS"]), "discontinuous": False}
              for p in d["phases"]]
    duration = d["durationS"]
    n = 600
    fs_out = n / duration

    with watch("ecgwave"):
        # the filtered ECG, mean-pooled 248 → 62 Hz: QRS complexes stay visible
        ecg = np.asarray(d["signal"]["filtered"], dtype=np.float64)
        ecg = ecg[: len(ecg) // 4 * 4].reshape(-1, 4).mean(1)
        ecg_fs = d["signal"]["fs"] / 4
    with watch("hr"):
        # instantaneous HR from valid RR intervals, onto an even grid
        t = np.asarray(d["rr"]["t"]); ms = np.asarray(d["rr"]["ms"]); ok = np.asarray(d["rr"]["valid"])
        hr = np.interp(np.arange(n) / fs_out, t[ok], 60000.0 / ms[ok])
    with watch("emg"):
        # muscle activity: rectify the EMG, then average onto the same grid
        emg_raw = d["companions"]["emg"]
        emg = downsample(np.abs(np.asarray(emg_raw["values"], dtype=np.float64)), n)

    hrv = d["hrv"]["phases"]
    names = [p["name"] for p in phases]
    rest, city = names[0], names[-1]
    emg_mean = phase_mean(emg, fs_out, phases)

    with watch("fuse"):
        # decision-level fusion across the two modalities: does each signal move the way stress predicts?
        votes = [
            ("hr", "Heart rate (ECG)", hrv[city]["mean_hr_bpm"] > hrv[rest]["mean_hr_bpm"],
             f"{hrv[rest]['mean_hr_bpm']:.0f} → {hrv[city]['mean_hr_bpm']:.0f} bpm"),
            ("rmssd", "Heart-rate variability (ECG)", hrv[city]["rmssd_ms"] < hrv[rest]["rmssd_ms"],
             f"{hrv[rest]['rmssd_ms']:.0f} → {hrv[city]['rmssd_ms']:.0f} ms"),
            ("emg", "Muscle tension (EMG)", emg_mean[city] > emg_mean[rest],
             f"{emg_mean[rest]:.2f} → {emg_mean[city]:.2f} a.u."),
        ]
    agree = sum(v[2] for v in votes)
    verdict = "Flagged" if agree == len(votes) else "Watch" if agree >= 2 else "Stable"

    rest_hr, rest_rmssd = hrv[rest]["mean_hr_bpm"], hrv[rest]["rmssd_ms"]
    hr_label, hr_level = hr_category(rest_hr)
    hrv_level = "routine" if rest_rmssd < 20 else "ok"
    findings = [
        finding(hr_label, f"{rest_hr:.0f} bpm at rest by ECG (normal 50–100)", hr_level),
        finding("Healthy heart-rate variability" if hrv_level == "ok" else "Low heart-rate variability",
                f"RMSSD {rest_rmssd:.0f} ms at rest (below 20 ms is low)", hrv_level),
        {"label": "Acute stress response while driving", "tone": "info",
         "detail": (f"Heart rate +{hrv[city]['mean_hr_bpm'] - rest_hr:.0f} bpm, HRV "
                    f"{(hrv[city]['rmssd_ms'] / rest_rmssd - 1) * 100:.0f}%, muscle tension "
                    f"×{emg_mean[city] / emg_mean[rest]:.0f} — the normal reaction to city traffic, not a disorder")},
    ]
    condition, advice_block = summarise(findings)

    metrics = [{"phase": name, "values": {
        "hr": r(hrv[name]["mean_hr_bpm"], 1), "rmssd": r(hrv[name]["rmssd_ms"], 1),
        "sdnn": r(hrv[name]["sdnn_ms"], 1), "pnn50": r(hrv[name]["pnn50_pct"], 1),
        "emg": r(emg_mean[name], 2), "artifact": r(hrv[name]["artifact_pct"], 1)}} for name in names]

    return {
        "id": "drivedb-drive05",
        "source": {"dataset": "PhysioNet drivedb", "kind": "public", "url": d["source"]["url"],
                   "note": f"{d['source']['author']}. ECG and EMG only, from Hans's ECG dashboard export."},
        "subject": {"id": d["subject"]["id"], "age": None, "sex": None, "bmi": None},
        "label": d["label"],
        "recordedOn": None,
        "durationS": duration,
        "modalities": [
            {"key": "ecg", "label": "ECG", "detail": f"{d['device']['lead']}, {d['device']['fs']:.0f} Hz"},
            {"key": "emg", "label": "EMG", "detail": f"Shoulder muscle, {emg_raw['fs']} Hz"},
        ],
        "phases": phases,
        "tracks": [
            {"key": "ecgWave", "group": "ecgwave", "label": "ECG", "unit": "mV", "fs": r(ecg_fs, 3), "values": series(ecg, 3)},
            {"key": "ecg", "group": "hr", "label": "Heart rate (ECG)", "unit": "bpm", "fs": r(fs_out, 4), "values": series(hr, 1)},
            {"key": "emg", "group": "emg", "label": "Muscle tension (EMG)", "unit": "a.u.", "fs": r(fs_out, 4), "values": series(emg, 3)},
        ],
        "metricDefs": [
            {"key": "hr", "label": "Mean heart rate", "unit": "bpm", "digits": 1},
            {"key": "rmssd", "label": "RMSSD", "unit": "ms", "digits": 1},
            {"key": "sdnn", "label": "SDNN", "unit": "ms", "digits": 1},
            {"key": "pnn50", "label": "pNN50", "unit": "%", "digits": 1},
            {"key": "emg", "label": "Muscle tension (EMG)", "unit": "a.u.", "digits": 2},
            {"key": "artifact", "label": "Artifact beats", "unit": "%", "digits": 1, "lowerIsBetter": True},
        ],
        "metrics": metrics,
        "quality": {"status": d["quality"]["status"], "message": d["quality"]["message"]},
        "fusion": {
            "title": "Stress response",
            "method": "Decision-level fusion of ECG and EMG · each signal votes on whether it moved the way stress predicts",
            "score": agree, "scoreMax": len(votes), "band": f"{agree} of {len(votes)} signals",
            "verdict": verdict,
            "stats": [
                {"label": "LF/HF ratio", "value": f"{d['hrv']['frequency']['lf_hf_ratio']:.2f}", "hint": "Whole session"},
                {"label": "Artifact beats", "value": f"{d['hrv']['session']['artifact_pct']:.1f}%", "hint": "Excluded from HRV"},
                {"label": "Beats analysed", "value": f"{d['hrv']['session']['beats']:.0f}", "hint": "Valid R-R intervals"},
            ],
            "parts": [{"key": k, "label": label, "reading": reading, "points": 1 if moved else 0}
                      for k, label, moved, reading in votes],
            "note": (f"{agree} of {len(votes)} signals across ECG and EMG shifted toward stress between "
                     f"{rest.lower()} and {city.lower()} driving — two modalities agreeing is what makes it credible."),
        },
        "assessment": {"condition": condition, "findings": findings, "advice": advice_block, "disclaimer": DISCLAIMER},
        "pipeline": [
            {"stage": "Load export", "modality": "ecg", "status": "ok", "ms": r(watch.ms["load"], 0),
             "detail": f"{len(d['signal']['raw'])} ECG samples at {d['signal']['fs']:.0f} Hz with R-peaks from Hans's pipeline"},
            {"stage": "R-peak detection", "modality": "ecg", "status": "ok", "ms": None,
             "detail": f"{len(d['rPeaks'])} R-peaks, {d['hrv']['session']['artifact_pct']:.1f}% flagged as artifact — upstream"},
            {"stage": "Waveform decimation", "modality": "ecg", "status": "ok", "ms": r(watch.ms["ecgwave"], 1),
             "detail": "Filtered ECG mean-pooled from 248 to 62 Hz for display — QRS complexes stay visible"},
            {"stage": "Instantaneous HR", "modality": "ecg", "status": "ok", "ms": r(watch.ms["hr"], 1),
             "detail": "Valid R-R intervals converted to bpm and interpolated onto an even 2 Hz grid"},
            {"stage": "EMG envelope", "modality": "emg", "status": "ok", "ms": r(watch.ms["emg"], 1),
             "detail": f"EMG rectified and averaged from {emg_raw['fs']} Hz onto the same 2 Hz grid"},
            {"stage": "Stress vote", "modality": "all", "status": "ok", "ms": r(watch.ms["fuse"], 2),
             "detail": "Heart rate, HRV and muscle tension compared with the direction stress predicts"},
        ],
    }


def build_thermal():
    watch = Stopwatch()
    with watch("load"):
        d = fetch("thermal/S01.json")
    phases = [{"name": p["name"], "startS": r(p["startS"]), "endS": r(p["endS"]), "discontinuous": False}
              for p in d["phases"]]
    fs = d["series"]["rateHz"]
    rois = [roi for roi in d["rois"] if roi["valid"]]
    roi_series = d["series"]["roiMeanC"]
    with watch("phases"):
        means = {roi["key"]: phase_mean(roi_series[roi["key"]], fs, phases) for roi in rois}
    names = [p["name"] for p in phases]

    # the ROI that moves most during the middle phase is the one the activity touched
    with watch("fuse"):
        deltas = {k: means[k][names[1]] - means[k][names[0]] for k in means}
    lead = max(deltas, key=lambda k: abs(deltas[k]))
    label_of = {roi["key"]: roi["label"] for roi in rois}

    assessment = {
        "condition": "Not assessable from this recording",
        "findings": [{"label": "Thermal signature of drinking", "tone": "info",
                      "detail": f"{label_of[lead]} {deltas[lead]:+.2f} °C during {names[1].lower()} — explains the activity, not the person's health"}],
        "advice": {"level": "na", "answer": "Not applicable",
                   "text": "No medical conclusion can be drawn — the temperatures are illustrative."},
        "disclaimer": DISCLAIMER,
    }

    return {
        "assessment": assessment,
        "id": "thermal-s01",
        "source": {"dataset": "Wikimedia Commons thermography", "kind": "public", "url": d["source"]["url"],
                   "note": "Temperatures are reconstructed from a false-colour palette and are illustrative. Converted from Hans's thermal dashboard export."},
        "subject": {"id": d["subject"]["id"], "age": None, "sex": None, "bmi": None},
        "label": d["label"],
        "recordedOn": None,
        "durationS": d["durationS"],
        "modalities": [{"key": "thermal", "label": "Thermal", "detail": f"{d['device']['model']}, {d['device']['sensor']}"}],
        "phases": phases,
        "tracks": [{"key": f"t-{roi['key']}", "group": "thermal", "label": roi["label"], "unit": "°C", "fs": fs,
                    "values": series(roi_series[roi["key"]], 2)} for roi in rois],
        "metricDefs": [{"key": roi["key"], "label": roi["label"], "unit": "°C", "digits": 2} for roi in rois],
        "metrics": [{"phase": name, "values": {k: r(means[k][name], 2) for k in means}} for name in names],
        "quality": {"status": "illustrative", "message": "Single modality, palette-reconstructed temperatures."},
        "fusion": {
            "title": "Single modality",
            "method": "Fusion needs two or more co-recorded channels — this session has one",
            "score": None, "scoreMax": None, "band": "Not applicable", "verdict": "Single channel",
            "stats": [{"label": "Largest change", "value": f"{label_of[lead]} {deltas[lead]:+.2f} °C",
                       "hint": f"{names[0]} → {names[1]}"}],
            "parts": [{"key": k, "label": label_of[k], "reading": f"{deltas[k]:+.2f} °C", "points": None}
                      for k in means],
            "note": (f"The {label_of[lead].lower()} region cools by {abs(deltas[lead]):.1f} °C during "
                     f"{names[1].lower()} — the thermal signature of the activity. Pair it with a co-recorded "
                     "camera or ECG channel and it becomes fusable."),
        },
        "pipeline": [
            {"stage": "Load export", "modality": "thermal", "status": "ok", "ms": r(watch.ms["load"], 0),
             "detail": f"{d['frames']['count']} frames, {len(rois)} ROIs at {fs} Hz from Hans's thermal pipeline"},
            {"stage": "ROI validity", "modality": "thermal", "status": "degraded" if any(d["roiValidity"].values()) else "ok",
             "ms": None, "detail": "Hair over the forehead flagged — forehead readings are less reliable"
             if d["roiValidity"].get("hairOverForehead") else "All ROIs clear"},
            {"stage": "Phase averages", "modality": "thermal", "status": "ok", "ms": r(watch.ms["phases"], 2),
             "detail": "Mean ROI temperature within each annotated phase"},
            {"stage": "Change detection", "modality": "thermal", "status": "ok", "ms": r(watch.ms["fuse"], 2),
             "detail": "ROI with the largest shift into the activity phase"},
        ],
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    print("MCD-rPPG — camera pulse")
    sessions = build_mcd()
    print("drivedb — ECG and EMG")
    sessions.append(build_ecg())
    print("thermal — facial ROIs")
    sessions.append(build_thermal())

    for name in os.listdir(OUT):
        if name.endswith(".json"):
            os.remove(os.path.join(OUT, name))
    for s in sessions:
        with open(os.path.join(OUT, f"{s['id']}.json"), "w") as f:
            json.dump(s, f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {len(sessions)} sessions to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
