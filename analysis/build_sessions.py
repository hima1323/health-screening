"""
Build the study sessions the timeline shows, one JSON file per session.

Three sources, one shape:
  MCD-rPPG   PhysFormer run on each sitting's face video, against the contact
             PPG and the clinical readings taken at the same sitting
  drivedb    Hans's ECG session: ECG-derived heart rate plus the respiration
             and skin-conductance channels recorded on the same clock
  thermal    Hans's thermal session: four facial ROIs through a cold drink

Every stage is timed, so the pipeline the dashboard draws is the one that ran.

    python analysis/build_sessions.py
"""
import csv
import subprocess
import json
import math
import os
import sys
import time

import numpy as np
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RPPG = os.path.join(ROOT, "rppg1")
sys.path[:0] = [RPPG, os.path.join(RPPG, "webapp")]
from model import PhysFormer  # noqa: E402
import vitals  # noqa: E402

OUT = os.path.join(ROOT, "server", "data", "sessions")
CACHE = os.path.join(ROOT, "analysis", "sources")
MCD = os.path.join(RPPG, "data")
CKPT = os.path.join(RPPG, "checkpoints_mcd", "physformer_last.pt")
HANS = "repos/h4444n55555/Multimodal-Analysis-Dashboards/contents/website/public/data"

FPS = 30.0
CLIP = 96
STRIDE = 48


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


# ── NEWS2 ─────────────────────────────────────────────────────────────────
# Royal College of Physicians, National Early Warning Score 2 (2017).
# Consciousness and supplemental oxygen are not recorded in MCD; the
# participants were alert and on room air, which both score 0.

def _band(v, bands):
    for test, points in bands:
        if test(v):
            return points
    return 0


def news2_points(resp, spo2, sys_bp, pulse, temp):
    return {
        "resp": _band(resp, [(lambda v: v <= 8, 3), (lambda v: v <= 11, 1), (lambda v: v <= 20, 0),
                             (lambda v: v <= 24, 2), (lambda v: True, 3)]),
        "spo2": _band(spo2, [(lambda v: v <= 91, 3), (lambda v: v <= 93, 2), (lambda v: v <= 95, 1),
                             (lambda v: True, 0)]),
        "sys": _band(sys_bp, [(lambda v: v <= 90, 3), (lambda v: v <= 100, 2), (lambda v: v <= 110, 1),
                              (lambda v: v <= 219, 0), (lambda v: True, 3)]),
        "pulse": _band(pulse, [(lambda v: v <= 40, 3), (lambda v: v <= 50, 1), (lambda v: v <= 90, 0),
                               (lambda v: v <= 110, 1), (lambda v: v <= 130, 2), (lambda v: True, 3)]),
        "temp": _band(temp, [(lambda v: v <= 35.0, 3), (lambda v: v <= 36.0, 1), (lambda v: v <= 38.0, 0),
                             (lambda v: v <= 39.0, 1), (lambda v: True, 2)]),
    }


def news2_band(points):
    total = sum(points.values())
    if total >= 7:
        return total, "High", "Flagged"
    if total >= 5 or max(points.values()) == 3:
        return total, "Medium", "Watch"
    return total, "Low", "Stable"


# ── MCD-rPPG ──────────────────────────────────────────────────────────────

def load_model():
    model = PhysFormer(dim=48, ff_hidden=72, depth=6, heads=4, theta=0.7, tau=2.0,
                       tube_size=(4, 4, 4), frames=CLIP, norm_type="bn")
    model.load_state_dict(torch.load(CKPT, map_location="cpu"))
    return model.eval()


def infer(model, frames):
    """Sliding 96-frame windows, Hann-weighted overlap-add into one waveform."""
    n = len(frames)
    starts = list(range(0, n - CLIP + 1, STRIDE))
    if starts[-1] != n - CLIP:
        starts.append(n - CLIP)
    acc, weight = np.zeros(n), np.zeros(n)
    window = np.hanning(CLIP) + 1e-3
    clip_all = torch.from_numpy(frames.astype(np.float32) / 255.0).permute(3, 0, 1, 2)
    with torch.no_grad():
        for s in starts:
            pred = model(clip_all[:, s:s + CLIP].unsqueeze(0)).squeeze(0).numpy()
            pred = (pred - pred.mean()) / (pred.std() + 1e-8)
            acc[s:s + CLIP] += pred * window
            weight[s:s + CLIP] += window
    return acc / weight, len(starts)


def pos(frames):
    """Plane-Orthogonal-to-Skin, Wang et al., IEEE TBME 2017 — training-free rPPG."""
    rgb = frames.reshape(len(frames), -1, 3).mean(1).astype(np.float64)
    L = int(1.6 * FPS)
    out = np.zeros(len(rgb))
    project = np.array([[0, 1, -1], [-2, 1, 1]])
    for t in range(len(rgb) - L + 1):
        s = (rgb[t:t + L] / rgb[t:t + L].mean(0)) @ project.T
        h = s[:, 0] + s[:, 1] * (s[:, 0].std() / (s[:, 1].std() + 1e-9))
        out[t:t + L] += h - h.mean()
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


def build_mcd(model):
    db = read_db()
    processed = os.path.join(MCD, "processed_mcd")
    by_subject = {}
    for name in sorted(os.listdir(processed)):
        pid, _, step = name.split("_")
        by_subject.setdefault(pid, {})[step] = os.path.join(processed, name)

    sessions = []
    for pid, steps in sorted(by_subject.items()):
        watch = Stopwatch()
        phases, tracks_rppg, tracks_ppg, metrics = [], [], [], []
        order = [s for s in ("before", "after") if s in steps]
        windows = 0

        for i, step in enumerate(order):
            row = db[(pid, step)]
            with watch("load"):
                frames = np.load(os.path.join(steps[step], "frames.npy"))
                contact = np.load(os.path.join(steps[step], "wave.npy"))
            with watch("pos"):
                pred = pos(frames)
            with watch("infer"):
                net, w = infer(model, frames)
                windows += w
            with watch("filter"):
                rppg_f = vitals.bandpass(pred, FPS, *vitals.HR_BAND_HZ)
                net_f = vitals.bandpass(net, FPS, *vitals.HR_BAND_HZ)
                ppg_f = vitals.bandpass(contact, FPS, *vitals.HR_BAND_HZ)
            with watch("estimate"):
                rppg_hr = vitals.estimate_hr(pred, FPS)
                net_hr = vitals.estimate_hr(net, FPS)
                ppg_hr = vitals.estimate_hr(contact, FPS)
                snr = vitals.signal_quality_db(pred, FPS)
                corr = float(np.corrcoef(rppg_f, ppg_f)[0, 1])
                net_corr = float(np.corrcoef(net_f, ppg_f)[0, 1])

            start = i * len(pred) / FPS
            phases.append({"name": "Before" if step == "before" else "After",
                           "startS": r(start), "endS": r(start + len(pred) / FPS),
                           "discontinuous": i > 0,
                           "note": "Resting" if step == "before" else "After a short exercise bout"})
            tracks_rppg.extend(series(z(rppg_f)))
            tracks_ppg.extend(series(z(ppg_f)))

            clinical = {k: float(row[k]) for k in ("pulse", "saturation", "temperature",
                                                   "respiratory", "upper_ap", "lower_ap", "stress")}
            with watch("fuse"):
                ref = news2_points(clinical["respiratory"], clinical["saturation"],
                                   clinical["upper_ap"], clinical["pulse"], clinical["temperature"])
                cam = dict(ref, pulse=news2_points(0, 99, 120, rppg_hr, 37)["pulse"])
            metrics.append({
                "phase": phases[-1]["name"],
                "values": {
                    "rppgHr": r(rppg_hr, 1), "ppgHr": r(ppg_hr, 1), "pulse": r(clinical["pulse"], 0),
                    "hrError": r(abs(rppg_hr - clinical["pulse"]), 1), "waveCorr": r(corr, 2),
                    "netHr": r(net_hr, 1), "netError": r(abs(net_hr - clinical["pulse"]), 1),
                    "netCorr": r(net_corr, 2),
                    "snrDb": r(snr, 1), "spo2": r(clinical["saturation"], 0),
                    "tempC": r(clinical["temperature"], 1), "resp": r(clinical["respiratory"], 0),
                    "bpSys": r(clinical["upper_ap"], 0), "bpDia": r(clinical["lower_ap"], 0),
                    "stress": r(clinical["stress"], 0),
                    "news2": sum(ref.values()), "news2Camera": sum(cam.values()),
                },
                "_ref": ref, "_cam": cam,
            })

        # screening is judged at rest; the exercise sitting shows the response
        rest = metrics[0]
        total, band, verdict = news2_band(rest["_ref"])
        cam_total, cam_band, _ = news2_band(rest["_cam"])
        errors = [m["values"]["hrError"] for m in metrics]
        corrs = [m["values"]["waveCorr"] for m in metrics]
        net_errors = [m["values"]["netError"] for m in metrics]
        quality = "good" if np.mean(corrs) > 0.5 else "fair" if np.mean(corrs) > 0.25 else "poor"
        v = rest["values"]
        labels = {"resp": ("Respiration", f"{v['resp']:.0f} /min"),
                  "spo2": ("SpO₂", f"{v['spo2']:.0f}%"),
                  "sys": ("Systolic BP", f"{v['bpSys']:.0f} mmHg"),
                  "pulse": ("Pulse", f"{v['pulse']:.0f} bpm"),
                  "temp": ("Temperature", f"{v['tempC']:.1f} °C")}

        fusion = {
            "title": "NEWS2 early-warning score",
            "method": "Royal College of Physicians NEWS2 (2017), resting sitting · consciousness and oxygen assumed alert, room air",
            "score": total, "scoreMax": 20, "band": band, "verdict": verdict,
            "stats": [
                {"label": "Camera HR error", "value": f"{np.mean(errors):.1f} bpm", "hint": "POS vs clinical pulse, mean over sittings"},
                {"label": "PhysFormer error", "value": f"{np.mean(net_errors):.1f} bpm", "hint": "Current checkpoint, for comparison"},
                {"label": "Waveform match", "value": f"r = {np.mean(corrs):.2f}", "hint": "Camera vs contact PPG, bandpassed"},
                {"label": "Camera-only NEWS2", "value": f"{cam_total} · {cam_band}",
                 "hint": "Same score with the pulse taken from the camera instead"},
            ],
            "parts": [{"key": k, "label": labels[k][0], "reading": labels[k][1], "points": pts}
                      for k, pts in rest["_ref"].items()],
            "note": (f"Swapping the pulse sensor for the camera {'keeps' if cam_band == band else 'changes'} "
                     f"this patient's risk band ({band} → {cam_band})."),
        }

        for m in metrics:
            m.pop("_ref"), m.pop("_cam")

        row = db[(pid, order[0])]
        sessions.append({
            "id": f"mcd-{pid}",
            "source": {"dataset": "MCD-rPPG", "kind": "public",
                       "url": "https://huggingface.co/datasets/dypknu/mcd_rppg",
                       "note": "Face video, contact PPG and clinical vitals from the same sitting."},
            "subject": {"id": pid, "age": int(float(row["age"])), "sex": row["sex"],
                        "bmi": r(float(row["bmi"]), 1)},
            "label": "Rest → after exercise" if len(order) == 2 else "Resting",
            "recordedOn": recorded_on(pid, order[0]),
            "durationS": r(len(order) * 10.0, 1),
            "modalities": [
                {"key": "rppg", "label": "Camera pulse", "detail": "POS on a FullHD webcam, 96 px face crop · PhysFormer compared"},
                {"key": "ppg", "label": "Contact PPG", "detail": "Finger sensor, synchronised to the video"},
                {"key": "clinical", "label": "Clinical", "detail": "Pulse oximeter, thermometer, cuff, respiration count"},
            ],
            "phases": phases,
            "tracks": [
                {"key": "rppg", "group": "pulse", "label": "Camera pulse", "unit": "z", "fs": FPS, "values": tracks_rppg},
                {"key": "ppg", "group": "pulse", "label": "Contact PPG", "unit": "z", "fs": FPS, "values": tracks_ppg},
            ],
            "metricDefs": [
                {"key": "rppgHr", "label": "Camera HR", "unit": "bpm", "digits": 1},
                {"key": "ppgHr", "label": "Contact PPG HR", "unit": "bpm", "digits": 1},
                {"key": "pulse", "label": "Clinical pulse", "unit": "bpm", "digits": 0},
                {"key": "hrError", "label": "Camera error", "unit": "bpm", "digits": 1, "lowerIsBetter": True},
                {"key": "netHr", "label": "PhysFormer HR", "unit": "bpm", "digits": 1},
                {"key": "netError", "label": "PhysFormer error", "unit": "bpm", "digits": 1, "lowerIsBetter": True},
                {"key": "waveCorr", "label": "Waveform r", "unit": "", "digits": 2},
                {"key": "snrDb", "label": "Camera SNR", "unit": "dB", "digits": 1},
                {"key": "spo2", "label": "SpO₂", "unit": "%", "digits": 0},
                {"key": "tempC", "label": "Temperature", "unit": "°C", "digits": 1},
                {"key": "resp", "label": "Respiration", "unit": "/min", "digits": 0},
                {"key": "bpSys", "label": "Systolic BP", "unit": "mmHg", "digits": 0},
                {"key": "bpDia", "label": "Diastolic BP", "unit": "mmHg", "digits": 0},
                {"key": "stress", "label": "Stress (self-report)", "unit": "/10", "digits": 0},
                {"key": "news2", "label": "NEWS2", "unit": "", "digits": 0, "lowerIsBetter": True},
            ],
            "metrics": metrics,
            "quality": {"status": quality,
                        "message": f"Camera waveform tracks the contact PPG at r = {np.mean(corrs):.2f}."},
            "fusion": fusion,
            "pipeline": [
                {"stage": "Face crop", "modality": "rppg", "status": "ok", "ms": None,
                 "detail": "Haar cascade on the first frame, 30% margin, resized to 96 px — done once in preprocessing"},
                {"stage": "Load and normalise", "modality": "rppg", "status": "ok", "ms": r(watch.ms["load"], 0),
                 "detail": f"{len(order) * 300} frames scaled to 0–1, arranged channel × time × H × W"},
                {"stage": "POS projection", "modality": "rppg", "status": "ok" if quality != "poor" else "degraded",
                 "ms": r(watch.ms["pos"], 1),
                 "detail": "Mean skin RGB projected onto the plane orthogonal to skin tone, 1.6 s windows — the camera channel used below"},
                {"stage": "PhysFormer inference", "modality": "rppg", "status": "degraded", "ms": r(watch.ms["infer"], 0),
                 "detail": f"{windows} windows of 96 frames, overlap-add · comparison only: {np.mean(net_errors):.0f} bpm error, "
                           f"r = {np.mean([m['values']['netCorr'] for m in metrics]):.2f} — the checkpoint needs retraining"},
                {"stage": "Bandpass", "modality": "all", "status": "ok", "ms": r(watch.ms["filter"], 1),
                 "detail": "0.7–3 Hz zero-phase Butterworth on camera and contact signals alike"},
                {"stage": "HR and quality", "modality": "all",
                 "status": "ok" if quality == "good" else "degraded", "ms": r(watch.ms["estimate"], 1),
                 "detail": "Periodogram peak for HR, harmonic SNR, Pearson r against the contact PPG"},
                {"stage": "NEWS2 fusion", "modality": "clinical", "status": "ok", "ms": r(watch.ms["fuse"], 2),
                 "detail": "Five vitals scored against NEWS2 bands, once with the clinical pulse and once with the camera's"},
            ],
        }
        )
        print(f"  mcd-{pid}: POS {', '.join(str(m['values']['rppgHr']) for m in metrics)} · "
              f"PhysFormer {', '.join(str(m['values']['netHr']) for m in metrics)} bpm "
              f"vs clinical {', '.join(str(m['values']['pulse']) for m in metrics)} · r={np.mean(corrs):.2f} "
              f"· NEWS2 {total} {band} (camera {cam_total} {cam_band})")
    return sessions


# ── Hans's sessions ───────────────────────────────────────────────────────

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


def build_ecg():
    watch = Stopwatch()
    with watch("load"):
        d = fetch("ecg/S01.json")
    phases = [{"name": p["name"], "startS": r(p["startS"]), "endS": r(p["endS"]), "discontinuous": False}
              for p in d["phases"]]
    duration = d["durationS"]
    n = 600
    fs_out = n / duration

    with watch("hr"):
        # instantaneous HR from valid RR intervals, onto an even grid
        t = np.asarray(d["rr"]["t"]); ms = np.asarray(d["rr"]["ms"]); ok = np.asarray(d["rr"]["valid"])
        grid = np.arange(n) / fs_out
        hr = np.interp(grid, t[ok], 60000.0 / ms[ok])
    with watch("companions"):
        comp = d["companions"]
        resp = downsample(comp["resp"]["values"], n)
        gsr_h = downsample(comp["handGSR"]["values"], n)
        gsr_f = downsample(comp["footGSR"]["values"], n)

    hrv = d["hrv"]["phases"]
    names = [p["name"] for p in phases]
    rest, city = names[0], names[-1]
    means = {"hr": phase_mean(hr, fs_out, phases), "gsrH": phase_mean(gsr_h, fs_out, phases),
             "gsrF": phase_mean(gsr_f, fs_out, phases), "resp": phase_mean(resp, fs_out, phases)}
    resp_rate = {}
    for p in phases:  # breaths/min from the respiration channel's spectral peak
        a, b = int(p["startS"] * comp["resp"]["fs"]), int(p["endS"] * comp["resp"]["fs"])
        f = vitals._band_peak_hz(comp["resp"]["values"][a:b], comp["resp"]["fs"], vitals.RR_BAND_HZ)
        resp_rate[p["name"]] = None if f is None else f * 60

    with watch("fuse"):
        # decision-level fusion: does each channel move the way sympathetic arousal predicts?
        votes = [
            ("hr", "Heart rate", hrv[city]["mean_hr_bpm"] > hrv[rest]["mean_hr_bpm"],
             f"{hrv[rest]['mean_hr_bpm']:.0f} → {hrv[city]['mean_hr_bpm']:.0f} bpm"),
            ("rmssd", "HRV (RMSSD)", hrv[city]["rmssd_ms"] < hrv[rest]["rmssd_ms"],
             f"{hrv[rest]['rmssd_ms']:.0f} → {hrv[city]['rmssd_ms']:.0f} ms"),
            ("gsrH", "Hand skin conductance", means["gsrH"][city] > means["gsrH"][rest],
             f"{means['gsrH'][rest]:.2f} → {means['gsrH'][city]:.2f}"),
            ("gsrF", "Foot skin conductance", means["gsrF"][city] > means["gsrF"][rest],
             f"{means['gsrF'][rest]:.2f} → {means['gsrF'][city]:.2f}"),
            ("resp", "Breathing rate", (resp_rate[city] or 0) > (resp_rate[rest] or 0),
             f"{resp_rate[rest]:.0f} → {resp_rate[city]:.0f} /min"),
        ]
        # a spectral peak pinned to the edge of the search band is drift, not breathing
        lo, hi = (f * 60 for f in vitals.RR_BAND_HZ)
        pinned = any(v is None or v <= lo + 0.5 or v >= hi - 0.5 for v in resp_rate.values())
    scored = [v for v in votes if not (v[0] == "resp" and pinned)]
    agree = sum(v[2] for v in scored)
    verdict = "Flagged" if agree >= 0.75 * len(scored) else "Watch" if agree >= 0.5 * len(scored) else "Stable"

    metrics = [{"phase": name, "values": {
        "hr": r(hrv[name]["mean_hr_bpm"], 1), "rmssd": r(hrv[name]["rmssd_ms"], 1),
        "sdnn": r(hrv[name]["sdnn_ms"], 1), "pnn50": r(hrv[name]["pnn50_pct"], 1),
        "resp": r(resp_rate[name], 0), "gsrH": r(means["gsrH"][name], 2), "gsrF": r(means["gsrF"][name], 2),
        "artifact": r(hrv[name]["artifact_pct"], 1)}} for name in names]

    return {
        "id": "drivedb-drive05",
        "source": {"dataset": "PhysioNet drivedb", "kind": "public", "url": d["source"]["url"],
                   "note": f"{d['source']['author']}. Converted from Hans's ECG dashboard export."},
        "subject": {"id": d["subject"]["id"], "age": None, "sex": None, "bmi": None},
        "label": d["label"],
        "recordedOn": None,
        "durationS": duration,
        "modalities": [
            {"key": "ecg", "label": "ECG", "detail": f"{d['device']['lead']}, {d['device']['fs']:.0f} Hz"},
            {"key": "resp", "label": "Respiration", "detail": "Chest belt, 31 Hz"},
            {"key": "gsr", "label": "Skin conductance", "detail": "Hand and foot electrodes, 31 Hz"},
        ],
        "phases": phases,
        "tracks": [
            {"key": "ecg", "group": "hr", "label": "Heart rate (ECG)", "unit": "bpm", "fs": r(fs_out, 4), "values": series(hr, 1)},
            {"key": "resp", "group": "resp", "label": "Respiration", "unit": "a.u.", "fs": r(fs_out, 4), "values": series(resp, 2)},
            {"key": "gsr", "group": "gsr", "label": "Hand GSR", "unit": "a.u.", "fs": r(fs_out, 4), "values": series(gsr_h, 3)},
            {"key": "gsrFoot", "group": "gsr", "label": "Foot GSR", "unit": "a.u.", "fs": r(fs_out, 4), "values": series(gsr_f, 3)},
        ],
        "metricDefs": [
            {"key": "hr", "label": "Mean heart rate", "unit": "bpm", "digits": 1},
            {"key": "rmssd", "label": "RMSSD", "unit": "ms", "digits": 1},
            {"key": "sdnn", "label": "SDNN", "unit": "ms", "digits": 1},
            {"key": "pnn50", "label": "pNN50", "unit": "%", "digits": 1},
            {"key": "resp", "label": "Breathing rate", "unit": "/min", "digits": 0},
            {"key": "gsrH", "label": "Hand GSR", "unit": "a.u.", "digits": 2},
            {"key": "gsrF", "label": "Foot GSR", "unit": "a.u.", "digits": 2},
            {"key": "artifact", "label": "Artifact beats", "unit": "%", "digits": 1, "lowerIsBetter": True},
        ],
        "metrics": metrics,
        "quality": {"status": d["quality"]["status"], "message": d["quality"]["message"]},
        "fusion": {
            "title": "Stress response",
            "method": "Decision-level fusion · each channel votes on whether it moved the way sympathetic arousal predicts",
            "score": agree, "scoreMax": len(scored), "band": f"{agree} of {len(scored)} channels",
            "verdict": verdict,
            "stats": [
                {"label": "LF/HF ratio", "value": f"{d['hrv']['frequency']['lf_hf_ratio']:.2f}", "hint": "Whole session"},
                {"label": "Artifact beats", "value": f"{d['hrv']['session']['artifact_pct']:.1f}%", "hint": "Excluded from HRV"},
                {"label": "Beats analysed", "value": f"{d['hrv']['session']['beats']:.0f}", "hint": "Valid R-R intervals"},
            ],
            "parts": [{"key": k, "label": label,
                       "reading": f"{reading} · band edge, not scored" if k == "resp" and pinned else reading,
                       "points": None if k == "resp" and pinned else (1 if moved else 0)}
                      for k, label, moved, reading in votes],
            "note": (f"{agree} of {len(scored)} independent channels shifted toward arousal between "
                     f"{rest.lower()} and {city.lower()} driving — agreement across sensors, not any one of them, "
                     "is what makes the reading credible."),
        },
        "pipeline": [
            {"stage": "Load export", "modality": "ecg", "status": "ok", "ms": r(watch.ms["load"], 0),
             "detail": f"{len(d['signal']['raw'])} samples at {d['signal']['fs']:.0f} Hz with R-peaks from Hans's ECG pipeline"},
            {"stage": "R-peak detection", "modality": "ecg", "status": "ok", "ms": None,
             "detail": f"{len(d['rPeaks'])} R-peaks, {d['hrv']['session']['artifact_pct']:.1f}% flagged as artifact — upstream"},
            {"stage": "Instantaneous HR", "modality": "ecg", "status": "ok", "ms": r(watch.ms["hr"], 1),
             "detail": "Valid R-R intervals converted to bpm and interpolated onto an even 2 Hz grid"},
            {"stage": "Companion resampling", "modality": "all", "status": "ok", "ms": r(watch.ms["companions"], 1),
             "detail": "Respiration and both GSR channels mean-pooled from 31 Hz onto the same 2 Hz grid"},
            {"stage": "Arousal vote", "modality": "all", "status": "ok", "ms": r(watch.ms["fuse"], 2),
             "detail": "Five per-phase changes compared with the direction sympathetic arousal predicts"},
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

    return {
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
    torch.set_num_threads(4)
    print("MCD-rPPG — PhysFormer inference")
    sessions = build_mcd(load_model())
    print("drivedb — ECG, respiration, GSR")
    sessions.append(build_ecg())
    print("thermal — facial ROIs")
    sessions.append(build_thermal())

    for s in sessions:
        with open(os.path.join(OUT, f"{s['id']}.json"), "w") as f:
            json.dump(s, f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {len(sessions)} sessions to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
