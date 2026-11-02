"""CVPR Lab ablation ladder on MCD-rPPG: phase1 -> phase2 -> phase3 -> phase4, each trained with the toolbox protocol
(64 train / 16 valid / 20 held-out test subjects, the same split as MCD_MCD), then also tested on UBFC-rPPG
(cross-dataset). Finished runs are skipped, interrupted ones resume.

    python -m bench.ladder [--presets phase1_physformer phase2_physics ...] [--epochs 10]      (from rppg1/)
"""
import argparse
import os
import subprocess
import sys

from bench.preprocess import ROOT

LADDER = ["phase1_physformer", "phase2_physics", "phase3_dualstream", "phase4_frequency"]
RESULTS = os.path.join(ROOT, "runs", "results")


def run(*args):
    print(">>", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="*", default=LADDER)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    for p in a.presets:
        name = f"CVPR_{p}_MCD"
        if not os.path.isfile(os.path.join(RESULTS, name + ".json")):
            run("bench.run", "train", "--arch", f"cvprlab:{p}", "--train", "mcd_IriunWebcam", "--test",
                "mcd_IriunWebcam", "--name", name, "--epochs", str(a.epochs), "--workers", str(a.workers))
        cross = f"CVPR_{p}_MCD_UBFC"
        if not os.path.isfile(os.path.join(RESULTS, cross + ".json")):
            run("bench.run", "test", "--arch", f"cvprlab:{p}", "--ckpt", os.path.join("runs", name, "best.pt"),
                "--test", "ubfc", "--train-label", "MCD-rPPG", "--name", cross, "--batch", "1")
    run("bench.run", "report")
    print("LADDER DONE", flush=True)


if __name__ == "__main__":
    main()
