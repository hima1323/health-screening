"""Longer / deeper CVPR Lab runs on MCD-rPPG, each followed by the UBFC cross-dataset test. Same split and protocol
as bench.ladder; finished runs are skipped, interrupted ones resume. Stops early once a run beats both targets.

    python -m bench.campaign            (from rppg1/)
"""
import json
import os
import subprocess
import sys

from bench.preprocess import ROOT

RESULTS = os.path.join(ROOT, "runs", "results")
# targets: best MCD MAE so far (rppg1 PhysFormer) and best UBFC MAE so far (phase4, 10 epochs)
TARGET_MCD, TARGET_UBFC = 2.04, 2.64

# (run name, arch, epochs, extra train args)
RUNS = [
    ("CVPR_P4_e30_MCD", "cvprlab:phase4_frequency", 30, []),
    ("CVPR_P4_d12_e30_MCD", "cvprlab:phase4_frequency,depth=12", 30, []),
    ("CVPR_P4_d12_e30_aug_MCD", "cvprlab:phase4_frequency,depth=12", 30, ["--augment"]),
    ("CVPR_P3_d12_e30_MCD", "cvprlab:phase3_dualstream,depth=12", 30, []),
]


def run(*args, retries=5):
    """Retries a crashed run (the 6 GB GPU occasionally fails with OOM / cuDNN errors on the depth-12 models);
    bench.run train resumes from the last saved epoch."""
    for attempt in range(retries + 1):
        print(">>", " ".join(args), flush=True)
        if subprocess.run([sys.executable, "-m", *args], cwd=ROOT).returncode == 0:
            return
        print(f"!! crashed (attempt {attempt + 1}); retrying", flush=True)
    raise SystemExit(f"gave up after {retries + 1} attempts: {' '.join(args)}")


def mae(name):
    return json.load(open(os.path.join(RESULTS, name + ".json")))["metrics"]["MAE"]


def main():
    for name, arch, epochs, extra in RUNS:
        if not os.path.isfile(os.path.join(RESULTS, name + ".json")):
            run("bench.run", "train", "--arch", arch, "--train", "mcd_IriunWebcam", "--test", "mcd_IriunWebcam",
                "--name", name, "--epochs", str(epochs), "--workers", "2", *extra)
        cross = name + "_UBFC"
        if not os.path.isfile(os.path.join(RESULTS, cross + ".json")):
            run("bench.run", "test", "--arch", arch, "--ckpt", os.path.join("runs", name, "best.pt"), "--test",
                "ubfc", "--train-label", "MCD-rPPG", "--name", cross, "--batch", "1")
        m, u = mae(name), mae(cross)
        print(f"RESULT {name}: MCD MAE {m:.2f}  UBFC MAE {u:.2f}", flush=True)
        if m < TARGET_MCD and u < TARGET_UBFC:
            print(f"TARGET BEATEN by {name}", flush=True)
            break
    print("CAMPAIGN DONE", flush=True)


if __name__ == "__main__":
    main()
