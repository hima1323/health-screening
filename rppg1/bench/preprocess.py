"""Preprocess raw videos into a cache, following the rPPG-Toolbox PhysFormer config
(configs/train_configs/PURE_PURE_UBFC-rPPG_PHYSFORMER_BASIC.yaml):
  face crop = Haar cascade on the first frame, largest face, box enlarged 1.5x (USE_LARGE_FACE_BOX, no dynamic
  detection); resize to 128 x 128; DiffNormalized input and label.

Per video the cache holds
  <id>.frames.npy   uint8 (T, 128, 128, 3) face crops (DiffNormalized is computed on the fly from these; storing uint8
                    instead of the toolbox's float32 chunks takes a quarter of the disk)
  <id>.json         fps, subject, frame-diff std over the whole video (the toolbox normalises by the whole-video std),
                    the raw PPG and its DiffNormalized form, and the mean RGB of the crop per frame (for POS)

    python -m bench.preprocess --dataset ubfc --raw data/raw/UBFC-rPPG/DATASET_2        (from rppg1/)
    python -m bench.preprocess --dataset pure --raw data/raw/PURE
    python -m bench.preprocess --dataset mcd  --raw data/raw/MCD-rPPG --camera IriunWebcam --max-seconds 60
"""
import argparse
import json
import os
import time

import cv2
import numpy as np

from bench.readers import READERS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
SIZE = 128
BOX_COEF = 1.5


def face_box(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = det.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    h, w = gray.shape
    if len(faces) == 0:
        return (0, 0, w, h), False
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    cx, cy, side = x + fw / 2, y + fh / 2, max(fw, fh) * BOX_COEF
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    return (x0, y0, int(min(w, cx + side / 2)) - x0, int(min(h, cy + side / 2)) - y0), True


def diff_std(frames, batch=256):
    """Std of (f[t+1] - f[t]) / (f[t+1] + f[t] + 1e-7) over the whole video, computed in batches (float64 sums)."""
    s = s2 = n = 0.0
    for a in range(0, len(frames) - 1, batch):
        f = frames[a:a + batch + 1].astype(np.float32)
        d = (f[1:] - f[:-1]) / (f[1:] + f[:-1] + 1e-7)
        s += float(d.sum(dtype=np.float64))
        s2 += float((d.astype(np.float64) ** 2).sum())
        n += d.size
    return float(np.sqrt(max(s2 / n - (s / n) ** 2, 1e-12)))


def diffnorm_label(ppg):
    d = np.diff(ppg)
    d = d / (np.std(d) + 1e-12)
    return np.append(d, 0.0)


class Cropper:
    """Face box from the first frame (no dynamic detection, as in the toolbox config), then crop + resize each frame."""

    def __init__(self, fallback=None):
        self.box, self.found, self.fallback = None, None, fallback

    def __call__(self, frame):
        if self.box is None:
            self.box, self.found = face_box(frame)
            if not self.found and self.fallback:
                self.box = self.fallback
        x, y, w, h = self.box
        return cv2.resize(frame[y:y + h, x:x + w], (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def process(v, load, out_dir, max_seconds=None):
    crop = Cropper(v.get("fallback_box"))
    crops, fps, ppg = load(v, crop, max_seconds)
    if len(crops) < 160:
        return None
    (x, y, w, h), found = crop.box, crop.found
    np.save(os.path.join(out_dir, v["video_id"] + ".frames.npy"), crops)
    meta = {"dataset": v["dataset"], "video_id": v["video_id"], "subject": v["subject"], "fps": fps,
            "n_frames": int(len(crops)), "face_found": found, "box": [int(x), int(y), int(w), int(h)],
            "frame_diff_std": diff_std(crops), "ppg": [float(p) for p in ppg],
            "label_diffnorm": [float(p) for p in diffnorm_label(ppg)],
            "rgb_mean": crops.reshape(len(crops), -1, 3).mean(axis=1).round(4).tolist()}
    with open(os.path.join(out_dir, v["video_id"] + ".json"), "w") as f:
        json.dump(meta, f)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(READERS), required=True)
    ap.add_argument("--raw", required=True, help="raw dataset folder")
    ap.add_argument("--camera", help="MCD-rPPG only: e.g. IriunWebcam, FullHDwebcam, USBVideo")
    ap.add_argument("--out", help="cache folder (default rppg1/data/cache/<dataset>)")
    ap.add_argument("--max-seconds", type=float, help="MCD-rPPG only: keep the first N seconds of each video")
    a = ap.parse_args()
    list_videos, load = READERS[a.dataset]
    vids = list_videos(a.raw, a.camera) if a.dataset == "mcd" else list_videos(a.raw)
    out = a.out or os.path.join(CACHE, a.dataset + (f"_{a.camera}" if a.camera else ""))
    os.makedirs(out, exist_ok=True)
    print(f"{len(vids)} videos from {a.raw} -> {out}", flush=True)
    t0 = time.time()
    for i, v in enumerate(vids, 1):
        if os.path.isfile(os.path.join(out, v["video_id"] + ".json")):
            print(f"[{i}/{len(vids)}] {v['video_id']} cached", flush=True)
            continue
        m = process(v, load, out, a.max_seconds)
        print(f"[{i}/{len(vids)}] {v['video_id']}: " + ("too short, skipped" if m is None else
              f"{m['n_frames']} frames @ {m['fps']} fps, face {'found' if m['face_found'] else 'NOT found'}") +
              f" ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
