"""P1 measurement agent: heart rate from a face video (remote photoplethysmography).

1. Face box from an OpenCV Haar cascade, re-detected every second (last box kept between detections); the skin ROI
   is the central part of the box (cheeks and nose, avoiding hair and background). Mean RGB per frame.
2. Pulse signal with two classic methods: POS (Wang et al., IEEE TBME 2017) and CHROM (de Haan & Jeanne,
   IEEE TBME 2013). HR = spectral peak in 42-180 bpm.
3. Two readings = the two halves of the recording (each >= 10 s), standing in for the brief's "repeat after 60 s";
   a recording shorter than 20 s gives one reading, which the rules treat as unconfirmed (re-measure).
4. Video keyframes make the colour jump once per keyframe interval (every 24 frames = 1 s on MCD-rPPG webcams),
   which reads as a 60 bpm "pulse": abrupt steps are removed, and when they repeat with a fixed period the codec
   frequency and its harmonics are ignored in the HR search (reported in the diagnostics).
5. quality = mean(SNR score, POS/CHROM agreement score) x share of frames with a face; the score ramps are
   placeholders in configs/triage/measurement.yaml until P6 calibrates them. The reported value is POS.
On MCD-rPPG subject 1020 (IriunWebcam, 180 s, before / after exercise) the four half-readings are within 0.5 bpm of
the synchronised contact PPG (75.7 / 76.6 and 75.8 / 85.1 bpm).

    python -m triage.measure.hr_rppg <video>          (from reasoning_model/src)
"""
import argparse
import json

import cv2
import numpy as np
import yaml

from triage.evidence import CONFIG
from triage.measure.spectral import HR_BAND_HZ, bandpass, halves, peak_hz, ramp, snr_db

P = yaml.safe_load((CONFIG / "measurement.yaml").read_text(encoding="utf-8"))["rppg"]


def _detector():
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def read_face_trace(path, max_seconds=180, detect_every_s=1.0):
    """Mean skin RGB per frame (NaN where no face yet), fps, share of frames with a face, a preview frame + box."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"cannot open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not 5 <= fps <= 240:
        fps = 30.0
    det, every = _detector(), max(1, int(round(fps * detect_every_s)))
    rgb, box, seen, preview, i = [], None, 0, None, 0
    while i < max_seconds * fps:
        ok, frame = cap.read()
        if not ok:
            break
        if i % every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scale = 320.0 / max(gray.shape)
            small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
            faces = det.detectMultiScale(small, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            if len(faces):
                x, y, w, h = (max(faces, key=lambda f: f[2] * f[3]) / min(scale, 1)).astype(int)
                box = (x, y, w, h)
                if preview is None:
                    preview = (cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), box)
        if box is None:
            rgb.append([np.nan] * 3)
        else:
            x, y, w, h = box
            roi = frame[y + int(0.25 * h): y + int(0.85 * h), x + int(0.2 * w): x + int(0.8 * w)]
            rgb.append(roi.reshape(-1, 3)[:, ::-1].mean(axis=0) if roi.size else [np.nan] * 3)
            seen += 1
        i += 1
    cap.release()
    rgb = np.array(rgb, dtype=np.float64)
    return rgb, float(fps), (seen / len(rgb) if len(rgb) else 0.0), preview


def _fill(rgb):
    """Interpolate NaN gaps per channel (frames before the first detection are dropped by the caller)."""
    out = rgb.copy()
    idx = np.arange(len(out))
    for c in range(3):
        ok = ~np.isnan(out[:, c])
        if ok.sum() >= 2:
            out[:, c] = np.interp(idx, idx[ok], out[ok, c])
    return out


def remove_steps(rgb, k=6.0):
    """Remove abrupt colour steps (video keyframes, sudden movement): a frame-to-frame change larger than
    median + k * MAD of the changes is set to zero and the trace is re-integrated. On MCD-rPPG webcam videos the
    keyframe every 24 frames (1 s) otherwise shows up as a 60 bpm 'pulse'. Returns (trace, share of steps removed)."""
    d = np.diff(rgb, axis=0)
    lum = np.abs(d).sum(axis=1)
    med = np.median(lum)
    mad = np.median(np.abs(lum - med)) + 1e-9
    steps = lum > med + k * 1.4826 * mad
    d[steps] = 0.0
    return np.vstack([rgb[:1], rgb[:1] + np.cumsum(d, axis=0)]), steps


def codec_bands(steps, fps, half_width=0.05):
    """If the removed steps repeat with a fixed period P frames (a keyframe interval), the codec also leaves a ramp at
    fps / P Hz and its harmonics; return those frequency bands so the HR search ignores them."""
    idx = np.flatnonzero(steps)
    if len(idx) < 6:
        return [], None
    gaps = np.diff(idx)
    gaps = gaps[gaps >= 4]                    # 1-3 frame gaps are movement bursts, not keyframes
    if len(gaps) < 5:
        return [], None
    period = int(np.bincount(gaps).argmax())
    multiple = np.abs(gaps / period - np.round(gaps / period)) * period <= 1   # missed keyframes give 2P, 3P, ...
    chance = 3.0 / period                     # a random gap lands within +-1 frame of a multiple of P
    if period < 4 or multiple.mean() < max(0.3, 3 * chance):
        return [], None
    f0 = fps / period
    return [(k * f0 - half_width, k * f0 + half_width) for k in range(1, 6)
            if HR_BAND_HZ[0] - half_width <= k * f0 <= HR_BAND_HZ[1] + half_width], period


def pos(rgb, fps, window_s=1.6):
    """Plane-Orthogonal-to-Skin pulse signal (Wang et al. 2017), overlap-added over 1.6 s windows."""
    n, l = len(rgb), max(2, int(window_s * fps))
    h = np.zeros(n)
    proj = np.array([[0, 1, -1], [-2, 1, 1]], dtype=np.float64)
    for t in range(n - l + 1):
        c = rgb[t:t + l]
        cn = c / (c.mean(axis=0) + 1e-9)
        s = cn @ proj.T
        p = s[:, 0] + (s[:, 0].std() / (s[:, 1].std() + 1e-9)) * s[:, 1]
        h[t:t + l] += p - p.mean()
    return h


def chrom(rgb, fps):
    """Chrominance-based pulse signal (de Haan & Jeanne 2013)."""
    rn = rgb / (rgb.mean(axis=0) + 1e-9)
    xs = 3 * rn[:, 0] - 2 * rn[:, 1]
    ys = 1.5 * rn[:, 0] + rn[:, 1] - 1.5 * rn[:, 2]
    xf, yf = bandpass(xs, fps, *HR_BAND_HZ), bandpass(ys, fps, *HR_BAND_HZ)
    if xf is None or yf is None:
        return None
    return xf - (xf.std() / (yf.std() + 1e-9)) * yf


def hr_from_rgb(rgb, fps):
    """Per-half HR (POS and CHROM), SNR and quality from a mean-RGB trace."""
    has_face = ~np.isnan(rgb).all(axis=1)
    rgb = _fill(rgb[int(np.argmax(has_face)):])        # drop the frames before the first face detection
    rgb, steps = remove_steps(rgb)
    excl, period = codec_bands(steps, fps)
    halves_out = []
    for a, b in halves(len(rgb), fps, P["min_half_seconds"]):
        seg = rgb[a:b]
        p = bandpass(pos(seg, fps), fps, *HR_BAND_HZ)
        c = chrom(seg, fps)
        hp = peak_hz(p, fps, HR_BAND_HZ, excl) if p is not None else None
        hc = peak_hz(c, fps, HR_BAND_HZ, excl) if c is not None else None
        snr = snr_db(p, fps, exclude=excl) if p is not None else None
        halves_out.append({"start_s": a / fps, "end_s": b / fps, "hr_pos": None if hp is None else round(hp * 60, 1),
                           "hr_chrom": None if hc is None else round(hc * 60, 1),
                           "snr_db": None if snr is None else round(snr, 2)})
    codec = {"steps_removed_share": round(float(steps.mean()), 4), "keyframe_period_frames": period,
             "ignored_bpm": [round((lo + hi) / 2 * 60, 1) for lo, hi in excl]}
    return rgb, halves_out, codec


def measure(path):
    """-> (measurement dict for the evidence record, diagnostics dict)."""
    rgb, fps, face_share, preview = read_face_trace(path)
    duration = len(rgb) / fps
    diag = {"fps": fps, "duration_s": round(duration, 1), "face_share": round(face_share, 3), "preview": preview}
    if face_share == 0 or duration < 5:
        diag["error"] = "no face found" if face_share == 0 else "recording shorter than 5 s"
        return ({"name": "heart_rate", "value": None, "unit": "bpm", "quality": 0.0, "source": "rppg"},
                {**diag, "face_found": face_share > 0})
    rgb, parts, codec = hr_from_rgb(rgb, fps)
    diag.update(halves=parts, codec=codec, signal=bandpass(pos(rgb, fps), fps, *HR_BAND_HZ), face_found=True)
    readings = [h["hr_pos"] for h in parts if h["hr_pos"] is not None]
    if not readings:
        return {"name": "heart_rate", "value": None, "unit": "bpm", "quality": 0.0, "source": "rppg"}, diag
    q_snr = min(ramp(h["snr_db"], *P["snr_db_ramp"]) for h in parts)
    q_agree = min(1 - ramp(abs(h["hr_pos"] - h["hr_chrom"]), *P["agreement_bpm_ramp"]) if h["hr_chrom"] else 0.0
                  for h in parts)
    quality = round((q_snr + q_agree) / 2 * face_share, 2)
    diag["quality_parts"] = {"snr": round(q_snr, 2), "pos_chrom_agreement": round(q_agree, 2),
                             "face_share": round(face_share, 2)}
    m = {"name": "heart_rate", "value": round(float(np.mean(readings)), 1), "unit": "bpm", "quality": quality,
         "source": "rppg"}
    if len(readings) >= 2:
        m["repeat_values"] = readings
    return m, diag


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    m, d = measure(ap.parse_args().video)
    d.pop("preview", None), d.pop("signal", None)
    print(json.dumps({"measurement": m, "diagnostics": d}, indent=1))
