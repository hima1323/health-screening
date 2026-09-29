"""
Preprocess UBFC-rPPG (DATASET_2 layout: subjectN/vid.avi + ground_truth.txt)
into the frames.npy / wave.npy / hr.npy layout expected by dataset.py.

Ground-truth format (UBFC-rPPG DATASET_2): 3 whitespace-separated rows of
equal length -
  row 0: PPG waveform samples
  row 1: instantaneous HR trace (bpm)
  row 2: timestamps (seconds)

For each subject we:
  1. Detect a face bounding box on the first frame (Haar cascade) and use
     that fixed crop across the whole clip (as in the paper's MTCNN-based
     first-frame crop-and-fix approach).
  2. Resize the cropped face to img_size x img_size.
  3. Resample the PPG waveform (and HR trace) from the ground-truth's
     sample rate onto the video's frame indices.
  4. Save frames.npy (T,H,W,3 uint8), wave.npy (T,) float32, hr.npy scalar.
"""
import argparse
import os

import cv2
import numpy as np


def detect_face_bbox(frame, margin=0.3):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    h_img, w_img = frame.shape[:2]
    if len(faces) == 0:
        # fall back to a centered square crop
        side = min(h_img, w_img)
        x = (w_img - side) // 2
        y = (h_img - side) // 2
        return x, y, side, side
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    mx, my = int(w * margin), int(h * margin)
    x0 = max(0, x - mx)
    y0 = max(0, y - my)
    x1 = min(w_img, x + w + mx)
    y1 = min(h_img, y + h + my)
    return x0, y0, x1 - x0, y1 - y0


def load_video_frames(path, bbox, img_size):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    x, y, w, h = bbox
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        crop = frame[y:y + h, x:x + w]
        crop = cv2.resize(crop, (img_size, img_size))
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        frames.append(crop)
    cap.release()
    return np.stack(frames, axis=0), fps


def load_ground_truth(path):
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(np.array([float(v) for v in line.split()], dtype=np.float64))
    wave, hr_trace, ts = rows[0], rows[1], rows[2]
    return wave, hr_trace, ts


def resample_to_frames(signal, src_len, dst_len):
    src_idx = np.linspace(0, 1, src_len)
    dst_idx = np.linspace(0, 1, dst_len)
    return np.interp(dst_idx, src_idx, signal)


def process_subject(subject_dir, out_dir, img_size=128, low_bpm=42, high_bpm=180):
    vid_path = os.path.join(subject_dir, "vid.avi")
    gt_path = os.path.join(subject_dir, "ground_truth.txt")
    if not (os.path.isfile(vid_path) and os.path.isfile(gt_path)):
        return None

    cap = cv2.VideoCapture(vid_path)
    ret, first_frame = cap.read()
    cap.release()
    if not ret:
        print(f"[skip] could not read first frame: {vid_path}")
        return None

    bbox = detect_face_bbox(first_frame)
    frames, fps = load_video_frames(vid_path, bbox, img_size)

    wave, hr_trace, ts = load_ground_truth(gt_path)
    wave_r = resample_to_frames(wave, len(wave), len(frames)).astype(np.float32)
    hr_r = resample_to_frames(hr_trace, len(hr_trace), len(frames)).astype(np.float32)

    hr_valid = hr_r[(hr_r >= low_bpm) & (hr_r <= high_bpm)]
    hr_scalar = float(np.mean(hr_valid)) if len(hr_valid) else float(np.mean(hr_r))

    name = os.path.basename(os.path.normpath(subject_dir))
    dst = os.path.join(out_dir, name)
    os.makedirs(dst, exist_ok=True)
    np.save(os.path.join(dst, "frames.npy"), frames)
    np.save(os.path.join(dst, "wave.npy"), wave_r)
    np.save(os.path.join(dst, "hr.npy"), np.array(hr_scalar, dtype=np.float32))

    print(f"[ok] {name}: frames={frames.shape} fps={fps:.1f} hr={hr_scalar:.1f} bpm")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-root", required=True, help="Path to UBFC-rPPG DATASET_2 folder")
    ap.add_argument("--out-root", required=True, help="Output preprocessed dataset folder")
    ap.add_argument("--img-size", type=int, default=128)
    args = ap.parse_args()

    os.makedirs(args.out_root, exist_ok=True)
    subjects = sorted(
        d for d in os.listdir(args.raw_root)
        if os.path.isdir(os.path.join(args.raw_root, d)) and d.startswith("subject")
    )
    processed = 0
    for s in subjects:
        subject_dir = os.path.join(args.raw_root, s)
        result = process_subject(subject_dir, args.out_root, img_size=args.img_size)
        if result is not None:
            processed += 1
    print(f"Done. Processed {processed}/{len(subjects)} subjects.")


if __name__ == "__main__":
    main()
