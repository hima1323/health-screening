"""Download a subset of MCD-rPPG (Egorov et al., ACM MM 2025; CC-BY-4.0; https://huggingface.co/datasets/dypknu/mcd_rppg):
for the first N patients (by id) that have both a 'before' and an 'after' video from one camera, fetch the video,
its frame-synchronised PPG (ppg_sync) and frame timestamps (meta). Resumable: existing files are skipped.

    python -m bench.download_mcd --n 100 --camera IriunWebcam          (from rppg1/)
"""
import argparse
import csv
import os
import time
import urllib.request

from bench.preprocess import ROOT

BASE = "https://huggingface.co/datasets/dypknu/mcd_rppg/resolve/main"
OUT = os.path.join(ROOT, "data", "raw", "MCD-rPPG")


def fetch(path):
    dest = os.path.join(OUT, path)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(f"{BASE}/{path}", dest + ".part")
            os.replace(dest + ".part", dest)
            return os.path.getsize(dest)
        except OSError as e:
            if attempt == 2:
                print(f"FAILED {path}: {e}", flush=True)
                return 0
            time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--camera", default="IriunWebcam")
    a = ap.parse_args()
    fetch("db.csv"), fetch("README.md")
    rows = [r for r in csv.DictReader(open(os.path.join(OUT, "db.csv"))) if r["camera"] == a.camera]
    steps = {}
    for r in rows:
        steps.setdefault(int(r["patient_id"]), {})[r["step"]] = r
    pids = sorted(p for p, s in steps.items() if {"before", "after"} <= s.keys())[:a.n]
    files = [r[k] for p in pids for r in steps[p].values() for k in ("video", "ppg_sync", "meta")]
    print(f"{len(pids)} patients, {len(files)} files -> {OUT}", flush=True)
    total, t0 = 0, time.time()
    for i, f in enumerate(files, 1):
        total += fetch(f)
        if i % 30 == 0 or i == len(files):
            print(f"[{i}/{len(files)}] {total / 1e9:.2f} GB new ({time.time() - t0:.0f}s)", flush=True)
    print("DOWNLOAD DONE", flush=True)


if __name__ == "__main__":
    main()
