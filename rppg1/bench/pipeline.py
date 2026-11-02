"""Run the whole rPPG benchmark with whatever datasets are present under rppg1/data/raw/:

  1. preprocess each dataset (cached; re-running skips finished videos)
  2. unsupervised baselines POS and CHROM on every dataset
  3. PhysFormer (rppg1) trainings, rPPG-Toolbox protocol:
       PURE -> UBFC-rPPG and UBFC-rPPG -> PURE      (the published cross-dataset pair)
       MCD-rPPG -> MCD-rPPG (20% of subjects held out), MCD-rPPG -> PURE, MCD-rPPG -> UBFC-rPPG
     a training whose result file exists is skipped; an interrupted one resumes from its last epoch
  4. runs/REPORT.md comparing every result with the published rPPG-Toolbox numbers

    python -m bench.pipeline [--epochs 10] [--only PURE_UBFC]          (from rppg1/)
"""
import argparse
import glob
import os
import subprocess
import sys

from bench.preprocess import CACHE, ROOT

RAW = os.path.join(ROOT, "data", "raw")
DATASETS = {   # cache name: (reader, raw folder, extra preprocess args)
    "ubfc": ("ubfc", os.path.join(RAW, "UBFC-rPPG", "DATASET_2"), []),
    "pure": ("pure", os.path.join(RAW, "PURE"), []),
    "mcd_IriunWebcam": ("mcd", os.path.join(RAW, "MCD-rPPG"), ["--camera", "IriunWebcam", "--max-seconds", "60"]),
}
TRAININGS = [("PURE_UBFC", "pure", "ubfc"), ("UBFC_PURE", "ubfc", "pure"),
             ("MCD_MCD", "mcd_IriunWebcam", "mcd_IriunWebcam"), ("MCD_PURE", "mcd_IriunWebcam", "pure"),
             ("MCD_UBFC", "mcd_IriunWebcam", "ubfc")]


def run(*args):
    print(">>", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], cwd=ROOT, check=True)


def has_raw(name):
    reader, raw, _ = DATASETS[name]
    pattern = {"ubfc": "subject*", "pure": "[0-9][0-9]-[0-9][0-9]", "mcd": os.path.join("video", "*.avi")}[reader]
    return bool(glob.glob(os.path.join(raw, pattern)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--only", nargs="*", help="training names to run, e.g. PURE_UBFC MCD_MCD")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    present = [n for n in DATASETS if has_raw(n)]
    print("datasets found:", present or "none", flush=True)
    for n in present:
        reader, raw, extra = DATASETS[n]
        run("bench.preprocess", "--dataset", reader, "--raw", raw, "--out", os.path.join(CACHE, n), *extra)
        if not os.path.isfile(os.path.join(ROOT, "runs", "results", f"CHROM_{n}.json")):
            run("bench.run", "pos", "--test", n)
    for name, tr, te in TRAININGS:
        if a.only and name not in a.only:
            continue
        if tr not in present or te not in present:
            print(f"skip {name}: needs {tr} and {te}", flush=True)
            continue
        if os.path.isfile(os.path.join(ROOT, "runs", "results", name + ".json")):
            print(f"skip {name}: already done", flush=True)
            continue
        run("bench.run", "train", "--train", tr, "--test", te, "--name", name, "--epochs", str(a.epochs),
            "--workers", str(a.workers))
    run("bench.run", "report")


if __name__ == "__main__":
    main()
