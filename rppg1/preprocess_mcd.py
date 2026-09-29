"""
Preprocess MCD-rPPG (https://huggingface.co/datasets/dypknu/mcd_rppg) into
the frames.npy / wave.npy / hr.npy layout expected by dataset.py.

Expected raw layout (as produced by download_mcd.py):
  data/raw_mcd/video/<patient>_<camera>_<step>.avi
  data/raw_mcd/ppg_sync/<patient>_<camera>_<step>.txt   (per-frame PPG value + confidence, one line per video frame)
  data/raw_mcd/meta/<patient>_<camera>_<step>.txt       (per-frame timestamps, informational only)
  data/raw_mcd/db.csv                                    (per-recording table incl. ground-truth `pulse` HR in bpm)

ppg_sync line count is 1:1 with decoded video frame count, so no
resampling is needed (unlike UBFC-rPPG's independent-sample-rate ground
truth).
"""
import argparse
import csv
import os

import cv2
import numpy as np

from preprocess_ubfc import detect_face_bbox


def load_ppg_sync(path):
    values = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            values.append(float(parts[0]))
    return np.array(values, dtype=np.float32)


def process_recording(row, raw_root, out_root, img_size=128, max_frames=None):
    video_path = os.path.join(raw_root, row["video"])
    ppg_path = os.path.join(raw_root, row["ppg_sync"])
    if not (os.path.isfile(video_path) and os.path.isfile(ppg_path)):
        return None

    cap = cv2.VideoCapture(video_path)
    ret, first_frame = cap.read()
    if not ret:
        cap.release()
        print(f"[skip] could not read first frame: {video_path}")
        return None
    bbox = detect_face_bbox(first_frame)
    x, y, w, h = bbox

    frames = []
    crop = first_frame[y:y + h, x:x + w]
    crop = cv2.resize(crop, (img_size, img_size))
    frames.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    while max_frames is None or len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        crop = frame[y:y + h, x:x + w]
        crop = cv2.resize(crop, (img_size, img_size))
        frames.append(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    cap.release()
    frames = np.stack(frames, axis=0)

    wave = load_ppg_sync(ppg_path)
    n = min(len(frames), len(wave))
    frames = frames[:n]
    wave = wave[:n]

    hr_scalar = float(row["pulse"])

    name = os.path.splitext(os.path.basename(row["video"]))[0]
    dst = os.path.join(out_root, name)
    os.makedirs(dst, exist_ok=True)
    np.save(os.path.join(dst, "frames.npy"), frames)
    np.save(os.path.join(dst, "wave.npy"), wave)
    np.save(os.path.join(dst, "hr.npy"), np.array(hr_scalar, dtype=np.float32))

    print(f"[ok] {name}: frames={frames.shape} hr={hr_scalar:.1f} bpm")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-root", required=True, help="Path to raw_mcd folder (containing video/, ppg_sync/, meta/, db.csv)")
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--img-size", type=int, default=128)
    ap.add_argument("--camera", type=str, default="FullHDwebcam")
    ap.add_argument("--max-frames", type=int, default=None, help="Truncate each recording to this many frames (disk-saving)")
    args = ap.parse_args()

    os.makedirs(args.out_root, exist_ok=True)
    with open(os.path.join(args.raw_root, "db.csv")) as f:
        rows = list(csv.DictReader(f))

    rows = [r for r in rows if r["camera"] == args.camera]
    # only process recordings whose video file was actually downloaded
    rows = [r for r in rows if os.path.isfile(os.path.join(args.raw_root, r["video"]))]

    processed = 0
    for row in rows:
        result = process_recording(row, args.raw_root, args.out_root, img_size=args.img_size, max_frames=args.max_frames)
        if result is not None:
            processed += 1
    print(f"Done. Processed {processed}/{len(rows)} recordings.")


if __name__ == "__main__":
    main()
