"""P1 measurement agent: temperature and breathing rate from a thermal recording.

Inputs: a .npy array (frames, height, width) in degrees C plus the frame rate, or the repo's own format
(<name>.frames.bin: one uint8 per pixel, linear from tempMinC to tempMaxC, described by <name>.json "frames").
- Temperature: per frame, the mean of the hottest 0.5% of skin pixels (>= 30 C), a stand-in for the inner canthus
  (Zhou et al. 2020) until landmark tracking exists, plus a calibration offset (configs/triage/measurement.yaml,
  placeholder until the P6 calibration session against a contact thermometer). Two readings = the medians of the
  two halves. Quality = share of frames with skin x stability over time.
- Breathing rate: the skin blocks whose temperature oscillates most in 0.1-0.7 Hz (around the nostrils when they
  are in view) are averaged; rate = spectral peak; needs >= 20 s. Quality = how concentrated the band power is
  around the peak.

    python -m triage.measure.thermal_vitals <file.npy --fps 8 | file.frames.bin --meta file.json>
"""
import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from triage.evidence import CONFIG
from triage.measure.spectral import RR_BAND_HZ, _spectrum, bandpass, halves, peak_hz, ramp

P = yaml.safe_load((CONFIG / "measurement.yaml").read_text(encoding="utf-8"))["thermal"]


def load(path, fps=None, meta=None):
    """-> (frames in degrees C as float32 (T, H, W), fps)."""
    path = Path(path)
    if path.suffix == ".npy":
        frames = np.load(path, allow_pickle=False).astype(np.float32)
        if frames.ndim != 3:
            raise ValueError("a thermal .npy must have shape (frames, height, width)")
        if not fps:
            raise ValueError("give the thermal frame rate for a .npy recording")
        return frames, float(fps)
    meta = meta if isinstance(meta, dict) else json.loads(Path(meta).read_text(encoding="utf-8"))
    f = meta.get("frames", meta)
    raw = np.fromfile(path, dtype=np.uint8)
    frames = raw[: f["count"] * f["height"] * f["width"]].reshape(f["count"], f["height"], f["width"])
    return f["tempMinC"] + frames.astype(np.float32) / 255 * (f["tempMaxC"] - f["tempMinC"]), float(f["fps"])


def temperature(frames, fps):
    hot = []
    for fr in frames:
        skin = fr[fr >= P["face_min_c"]]
        hot.append(np.nan if skin.size < 20 else
                   float(np.sort(skin)[-max(5, int(P["hot_pixel_fraction"] * skin.size)):].mean()))
    hot = np.array(hot)
    skin_share = float(np.mean(~np.isnan(hot)))
    if skin_share == 0:
        return {"name": "temperature", "value": None, "unit": "C", "quality": 0.0, "source": "thermal_canthus"}, \
            {"error": f"no pixels at or above {P['face_min_c']} C (no face in view?)", "series": hot}
    series = hot + P["canthus_offset_c"]
    ok = series[~np.isnan(series)]
    readings = [round(float(np.median(ok[a:b])), 2) for a, b in halves(len(ok), fps, 3.0)]
    q = round(skin_share * ramp(float(np.std(ok)), *P["stability_ramp_c"]), 2)
    m = {"name": "temperature", "value": round(float(np.mean(readings)), 2), "unit": "C", "quality": q,
         "source": "thermal_canthus"}
    if len(readings) >= 2:
        m["repeat_values"] = readings
    return m, {"series": series, "skin_share": round(skin_share, 3), "sd_c": round(float(np.std(ok)), 3),
               "offset_c": P["canthus_offset_c"]}


def resp_rate(frames, fps, block=4, top_share=0.05):
    t = len(frames)
    if t / fps < P["resp_min_seconds"]:
        return None, {"error": f"recording shorter than {P['resp_min_seconds']} s: breathing rate not measured"}
    h, w = (frames.shape[1] // block) * block, (frames.shape[2] // block) * block
    blocks = frames[:, :h, :w].reshape(t, h // block, block, w // block, block).mean(axis=(2, 4)).reshape(t, -1)
    skin = blocks.mean(axis=0) >= P["face_min_c"] - 2
    if skin.sum() < 4:
        return None, {"error": "too little skin in view for breathing rate"}
    scores = []
    for j in np.flatnonzero(skin):
        f, p = _spectrum(blocks[:, j], fps)
        band = (f >= RR_BAND_HZ[0]) & (f <= RR_BAND_HZ[1])
        scores.append((p[band].sum() / (p[(f > 0.03)].sum() + 1e-12), j) if f is not None else (0, j))
    scores.sort(reverse=True)
    chosen = [j for _, j in scores[:max(3, int(top_share * len(scores)))]]
    ref = bandpass(blocks[:, chosen[0]], fps, *RR_BAND_HZ)
    if ref is None:
        return None, {"error": "breathing signal too short to filter"}
    sig = np.zeros(t)
    for j in chosen:                                # align signs: nostril pixels cool on inhale, warm on exhale
        x = bandpass(blocks[:, j], fps, *RR_BAND_HZ)
        sig += np.sign(np.dot(x, ref) or 1) * x / (x.std() + 1e-9)
    readings = []
    for a, b in halves(t, fps, P["resp_min_seconds"]):
        f0 = peak_hz(sig[a:b], fps, RR_BAND_HZ)
        if f0:
            readings.append(round(f0 * 60, 1))
    f, p = _spectrum(sig, fps)
    band = (f >= RR_BAND_HZ[0]) & (f <= RR_BAND_HZ[1])
    f0 = f[band][np.argmax(p[band])]
    prominence = float(p[band & (np.abs(f - f0) <= 0.05)].sum() / p[band].sum())
    if not readings:
        return None, {"error": "no breathing peak found"}
    m = {"name": "resp_rate", "value": round(float(np.mean(readings)), 1), "unit": "/min",
         "quality": round(ramp(prominence, *P["resp_prominence_ramp"]), 2), "source": "thermal_nostril"}
    if len(readings) >= 2:
        m["repeat_values"] = readings
    return m, {"signal": sig, "prominence": round(prominence, 3), "blocks_used": len(chosen)}


def measure(path, fps=None, meta=None):
    frames, fps = load(path, fps, meta)
    temp, d_t = temperature(frames, fps)
    rr, d_r = resp_rate(frames, fps)
    diag = {"fps": fps, "frames": len(frames), "duration_s": round(len(frames) / fps, 1), "shape": frames.shape[1:],
            "temperature": d_t, "resp": d_r, "preview": frames[len(frames) // 2]}
    return [m for m in (temp, rr) if m is not None], diag


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--meta", help="the .json that describes a .frames.bin")
    a = ap.parse_args()
    ms, d = measure(a.path, a.fps, a.meta)
    for k in ("preview",):
        d.pop(k)
    d["temperature"].pop("series", None), d["resp"].pop("signal", None)
    print(json.dumps({"measurements": ms, "diagnostics": d}, indent=1, default=str))
