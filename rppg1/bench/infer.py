"""Run a trained model on your own video (or on live frames, see webapp/): same face crop, 128 x 128 resize,
DiffNormalized input, 160-frame windows and whole-video FFT heart rate as the benchmark.

    python -m bench.infer --list                                    (from rppg1/)
    python -m bench.infer --video my_face.mp4                       best all-round model (P4, 30 epochs)
    python -m bench.infer --video my_face.mp4 --model p4-12-flip    --plot pulse.png
    python -m bench.infer --benchmark                               all models on the preprocessed test sets
    python -m bench.infer --benchmark ubfc --model p4               (mcd = the 20 held-out subjects only)

Record ~30-60 s, face to the camera, still, evenly lit; the face box is fixed from the first frame.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.metrics import fft_hr, post_process                              # noqa: E402
from bench.preprocess import ROOT, SIZE, Cropper, diff_std                  # noqa: E402
from bench.run import T, build_model, evaluate, load_metas, needs_stmap, run_model, split_by_subject  # noqa: E402
from cvprlab.data.stmap import build_stmap                                  # noqa: E402

# short name -> (run folder under runs/, arch, description); all trained on MCD-rPPG (64 subjects, Iriun webcam)
MODELS = {
    "p4": ("CVPR_P4_e30_MCD", "cvprlab:phase4_frequency",
           "CVPR Lab P4, 4 blocks, 30 epochs - best all-round (MCD 1.96 / UBFC 4.48 / MPSC 3.52 MAE)"),
    "p4-12-flip": ("CVPR_P4_d12_e30_aug_MCD", "cvprlab:phase4_frequency,depth=12",
                   "CVPR Lab P4, 12 blocks + flip, 30 epochs - best on MCD / UBFC (1.71 / 1.86), weak on phone video"),
    "p4-12": ("CVPR_P4_d12_e30_MCD", "cvprlab:phase4_frequency,depth=12",
              "CVPR Lab P4, 12 blocks, 30 epochs (MCD 1.86 / UBFC 4.56 / MPSC 6.77)"),
    "physformer": ("MCD_MCD", "rppg1", "PhysFormer (rppg1), 10 epochs (MCD 2.04 / UBFC 5.36 / MPSC 4.96)"),
}
DEFAULT = "p4"
# benchmark test sets (preprocessed caches in data/cache/); MCD keeps only the held-out 20% of subjects, as in training
BENCH = {"mcd": "mcd_IriunWebcam", "ubfc": "ubfc", "mpsc": "mpsc"}


class Predictor:
    """One trained model; call with uint8 RGB face crops (N, 128, 128, 3) -> DiffNormalized rPPG prediction (N,)."""
    clip_len, img_size = T, SIZE

    def __init__(self, name=DEFAULT, device=None):
        run, arch, self.description = MODELS[name]
        self.name = name
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        ckpt = os.path.join(ROOT, "runs", run, "best.pt")
        if not os.path.isfile(ckpt):
            raise SystemExit(f"checkpoint not found: {ckpt}")
        self.model = build_model(arch).to(self.device).eval()
        self.model.load_state_dict(torch.load(ckpt, map_location=self.device)["model"])
        self.stmap = needs_stmap(self.model)

    @torch.no_grad()
    def window(self, frames, fps, std=None):
        """One window of exactly T frames (T+1 if the next frame is known, as in training)."""
        f = np.asarray(frames, dtype=np.float32)
        d = (f[1:] - f[:-1]) / (f[1:] + f[:-1] + 1e-7)
        d = d / (std or d.std() + 1e-12)
        if len(d) < T:                                     # the toolbox appends a zero frame at the end
            d = np.concatenate([d, np.zeros((T - len(d),) + d.shape[1:], np.float32)])
        x = torch.from_numpy(np.ascontiguousarray(d.transpose(3, 0, 1, 2)))[None].to(self.device)
        st = torch.from_numpy(build_stmap(f[:T]))[None] if self.stmap else torch.zeros(0)
        with torch.autocast("cuda", dtype=torch.float16, enabled=self.device.type == "cuda"):
            p = run_model(self.model, x, st, torch.tensor([float(fps)]), self.device)
        return p.float().cpu().numpy()[0]

    def __call__(self, frames, fps):
        """Whole recording: non-overlapping T-frame windows (the remainder is dropped, as in the benchmark)."""
        std = diff_std(frames)
        n = len(frames) // T
        return np.concatenate([self.window(frames[k * T:k * T + T + 1], fps, std) for k in range(n)])


def pulse(pred, fps):
    """DiffNormalized prediction -> band-passed pulse waveform (cumsum, detrend, 0.75-2.5 Hz)."""
    return post_process(pred, fps, diff_flag=True)


def read_faces(path, max_seconds=None):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    crop, frames = Cropper(), []
    while max_seconds is None or len(frames) < max_seconds * fps:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(crop(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    cap.release()
    return np.stack(frames) if frames else None, float(fps), crop.found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="video file of a face")
    ap.add_argument("--model", default=DEFAULT, choices=[*MODELS, "all"])
    ap.add_argument("--max-seconds", type=float, help="use only the first N seconds")
    ap.add_argument("--plot", help="save the pulse waveform and its spectrum to this PNG")
    ap.add_argument("--list", action="store_true", help="list the trained models")
    ap.add_argument("--benchmark", nargs="*", choices=list(BENCH), metavar="SET",
                    help="test on preprocessed datasets: mcd ubfc mpsc (default all)")
    a = ap.parse_args()
    if a.benchmark is not None:
        return benchmark(list(MODELS) if a.model == "all" else [a.model], a.benchmark or list(BENCH))
    if a.list or not a.video:
        for k, (run, _, desc) in MODELS.items():
            ok = os.path.isfile(os.path.join(ROOT, "runs", run, "best.pt"))
            print(f"  {k:12s} {desc}{'' if ok else '  [checkpoint missing]'}")
        if not a.video:
            print("\nusage: python -m bench.infer --video <file> [--model NAME|all] [--plot out.png]\n"
                  "       python -m bench.infer --benchmark [mcd ubfc mpsc] [--model NAME|all]")
        return
    frames, fps, found = read_faces(a.video, a.max_seconds)
    if frames is None or len(frames) < T:
        raise SystemExit(f"need at least {T} frames ({T / fps:.1f} s); got {0 if frames is None else len(frames)}")
    print(f"{a.video}: {len(frames)} frames @ {fps:.2f} fps ({len(frames) / fps:.1f} s), "
          f"face {'found' if found else 'NOT found - using the whole frame'}")
    names = list(MODELS) if a.model == "all" else [a.model]
    for name in names:
        p = Predictor(name)
        t0 = time.time()
        wave = pulse(p(frames, fps), fps)
        print(f"  {name:12s} heart rate {fft_hr(wave, fps):6.1f} bpm   ({time.time() - t0:.1f} s, {p.device.type})")
        if a.plot:
            save_plot(wave, fps, a.plot if len(names) == 1 else a.plot.replace(".png", f"_{name}.png"), name)


def benchmark(names, sets):
    tests = {}
    for k in sets:
        try:
            metas = load_metas(BENCH[k])
        except SystemExit as e:
            print(f"  skip {k}: {e}")
            continue
        tests[k] = split_by_subject(metas, 0.8)[1] if k == "mcd" else metas
    print(f"{'model':12s} {'test':5s} {'videos':>6s} {'MAE':>6s} {'RMSE':>6s} {'MAPE':>6s} {'r':>5s} {'<=5bpm':>7s}")
    for name in names:
        p = Predictor(name)
        for k, metas in tests.items():
            res, rows = evaluate(p.model, metas, 1, 0, p.device)
            ok = np.mean([abs(r["hr_pred"] - r["hr_label"]) <= 5 for r in rows]) * 100
            print(f"{name:12s} {k:5s} {res['n_videos']:6d} {res['MAE']:6.2f} {res['RMSE']:6.2f} {res['MAPE']:6.2f} "
                  f"{res['Pearson']:5.2f} {ok:6.0f}%", flush=True)


def save_plot(wave, fps, out, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import periodogram
    f, pw = periodogram(wave, fs=fps, nfft=1 << (len(wave) - 1).bit_length())
    m = (f >= 0.6) & (f <= 3.0)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.5))
    t = np.arange(len(wave)) / fps
    a1.plot(t, wave, lw=0.9, color="#c0392b")
    a1.set(xlabel="time (s)", title=f"Predicted pulse ({name}) - HR {fft_hr(wave, fps):.1f} bpm")
    a2.plot(f[m] * 60, pw[m], color="#2c3e50")
    a2.set(xlabel="bpm", ylabel="power")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"  plot -> {out}")


if __name__ == "__main__":
    main()
