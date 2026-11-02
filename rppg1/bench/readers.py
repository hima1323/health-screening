"""Raw dataset readers -> one record per video: frames, fps, the contact PPG resampled to one value per frame, and the
subject id (all splits are by subject). Each loader takes `fn`, applied to every RGB frame as it is read (the face
crop + resize), so a full-resolution video is never held in memory.

Layouts (as in rPPG-Toolbox):
  UBFC-rPPG DATASET_2   <root>/subjectN/vid.avi + ground_truth.txt (row 0 = PPG, row 1 = HR, row 2 = time s)
  PURE                  <root>/XX-YY/XX-YY/*.png + <root>/XX-YY/XX-YY.json   (also accepted: PNGs directly in
                        <root>/XX-YY/ and the json next to them); subject = XX
  MCD-rPPG              <root>/video/<id>_<camera>_<step>.avi + ppg_sync/<same>.txt (one PPG value per frame);
                        fps from meta/<same>.txt frame timestamps when present
  MPSC-rPPG             <root>/subject_XXX/trial_YYY/video/video.MOV + empatica_*/BVP.csv, tags.csv (E4 wrist BVP,
                        64 Hz; aligned with the hand-written start frames in MPSC_ALIGN)
"""
import glob
import json
import os
import re
from datetime import datetime

import cv2
import numpy as np


def resample(signal, n):
    """Linear resampling by index (rPPG-Toolbox BaseLoader.resample_ppg)."""
    signal = np.asarray(signal, dtype=np.float64)
    return np.interp(np.linspace(1, len(signal), n), np.arange(1, len(signal) + 1), signal)


def read_video(path, fn, max_frames=None):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    while max_frames is None or len(frames) < max_frames:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(fn(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    cap.release()
    return np.stack(frames) if frames else np.zeros((0, 1, 1, 3), np.uint8), float(fps)


# ---------------------------------------------------------------- UBFC-rPPG

def ubfc_videos(root):
    dirs = sorted(glob.glob(os.path.join(root, "subject*")), key=lambda d: int(re.sub(r"\D", "", os.path.basename(d))))
    return [{"dataset": "UBFC-rPPG", "video_id": os.path.basename(d), "subject": int(re.sub(r"\D", "", os.path.basename(d))),
             "dir": d} for d in dirs if os.path.isfile(os.path.join(d, "vid.avi"))]


def ubfc_load(v, fn, max_seconds=None):
    frames, _ = read_video(os.path.join(v["dir"], "vid.avi"), fn)
    with open(os.path.join(v["dir"], "ground_truth.txt")) as f:
        ppg = np.array([float(x) for x in f.readline().split()])
    return frames, 30.0, resample(ppg, len(frames))   # rPPG-Toolbox uses FS = 30 for UBFC-rPPG


# ---------------------------------------------------------------- PURE

def pure_videos(root):
    out = []
    for d in sorted(glob.glob(os.path.join(root, "[0-9][0-9]-[0-9][0-9]"))):
        name = os.path.basename(d)
        img_dir = os.path.join(d, name) if os.path.isdir(os.path.join(d, name)) else d
        js = next((p for p in (os.path.join(d, name + ".json"), os.path.join(root, name + ".json"),
                               os.path.join(img_dir, name + ".json")) if os.path.isfile(p)), None)
        if js and glob.glob(os.path.join(img_dir, "*.png")):
            out.append({"dataset": "PURE", "video_id": name, "subject": int(name.split("-")[0]), "dir": img_dir,
                        "json": js})
    return out


def pure_load(v, fn, max_seconds=None):
    files = sorted(glob.glob(os.path.join(v["dir"], "*.png")))
    frames = np.stack([fn(cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)) for p in files])
    with open(v["json"]) as f:
        ppg = [x["Value"]["waveform"] for x in json.load(f)["/FullPackage"]]
    return frames, 30.0, resample(ppg, len(frames))


# ---------------------------------------------------------------- MCD-rPPG

def mcd_videos(root, camera=None):
    out = []
    for p in sorted(glob.glob(os.path.join(root, "video", "*.avi"))):
        stem = os.path.splitext(os.path.basename(p))[0]
        pid, cam, step = stem.split("_")
        sync = os.path.join(root, "ppg_sync", stem + ".txt")
        if os.path.isfile(sync) and (camera is None or cam == camera):
            out.append({"dataset": "MCD-rPPG", "video_id": stem, "subject": int(pid), "video": p, "sync": sync,
                        "meta": os.path.join(root, "meta", stem + ".txt")})
    return out


def _fps_from_meta(path):
    stamps = []
    with open(path) as f:
        for line in f:
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    stamps.append(datetime.fromisoformat(parts[1].strip()).timestamp())
                except ValueError:
                    pass
    return (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) > 10 else None


def mcd_load(v, fn, max_seconds=None):
    """ppg_sync has one PPG value per frame, so the recording can be cut to max_seconds without resampling."""
    cap = cv2.VideoCapture(v["video"])
    fps = (_fps_from_meta(v["meta"]) if os.path.isfile(v["meta"]) else None) or cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    frames, _ = read_video(v["video"], fn, int(max_seconds * fps) if max_seconds else None)
    ppg = np.loadtxt(v["sync"])[:, 0]
    n = min(len(frames), len(ppg))
    return frames[:n], round(fps, 3), ppg[:n]


# ---------------------------------------------------------------- MPSC-rPPG

# Per trial (from each trial's empatica_e4/track.txt): the video frame where the recorded segment starts, and the
# index k of the E4 event mark that starts it; the segment runs from tags[k] to tags[k + 1] (E4 unix time). The
# notes index marks from the second tag on (evmarknp = tags[1:]), which every video's length confirms: each video
# ends 2-6 s after its segment. subject_003/trial_001 has no start frame in its notes and is left out.
MPSC_ALIGN = {"subject_001/trial_001": (307, 1), "subject_002/trial_001": (478, 1), "subject_002/trial_002": (159, 1),
              "subject_002/trial_003": (176, 1), "subject_003/trial_002": (1110, 1),
              "subject_004/trial_001": (216, 2), "subject_005/trial_001": (194, 1),
              "subject_006/trial_001": (676, 1), "subject_007/trial_001": (613, 1)}
# face box (x, y, w, h) from the notes' crop, used only where the detector finds no face in the first frame
MPSC_BOX = {"subject_007/trial_001": (400, 0, 1000, 1000)}


def mpsc_videos(root):
    out = []
    for key, (start, k) in MPSC_ALIGN.items():
        d = os.path.join(root, *key.split("/"))
        e4 = next((p for p in glob.glob(os.path.join(d, "empatica*")) if os.path.isfile(os.path.join(p, "BVP.csv"))),
                  None)
        if e4 and os.path.isfile(os.path.join(d, "video", "video.MOV")):
            out.append({"dataset": "MPSC-rPPG", "video_id": key.replace("/", "_"), "subject": int(key[8:11]),
                        "video": os.path.join(d, "video", "video.MOV"), "e4": e4, "start": start, "mark": k,
                        "fallback_box": MPSC_BOX.get(key)})
    return out


def mpsc_load(v, fn, max_seconds=None):
    """Video frames start .. start + segment length, and the E4 wrist BVP (64 Hz) over the same E4-time segment,
    resampled to one value per frame. Camera and watch were synchronised by hand, so expect some lag."""
    tags = np.loadtxt(os.path.join(v["e4"], "tags.csv"), ndmin=1)
    t0, t1 = tags[v["mark"]], tags[v["mark"] + 1]
    with open(os.path.join(v["e4"], "BVP.csv")) as f:
        bvp_start, bvp_fs = float(f.readline()), float(f.readline())
        bvp = np.array([float(x) for x in f])
    ppg = bvp[int(round((t0 - bvp_start) * bvp_fs)):int(round((t1 - bvp_start) * bvp_fs))]
    cap = cv2.VideoCapture(v["video"])
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(round((t1 - t0) * fps))
    for _ in range(v["start"]):
        cap.grab()
    frames = []
    while len(frames) < n:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(fn(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    cap.release()
    ppg = resample(ppg, n)[:len(frames)]
    return np.stack(frames), round(fps, 3), ppg


READERS = {"ubfc": (ubfc_videos, ubfc_load), "pure": (pure_videos, pure_load), "mcd": (mcd_videos, mcd_load),
           "mpsc": (mpsc_videos, mpsc_load)}
