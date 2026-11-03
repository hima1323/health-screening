"""Train and benchmark the rppg1 PhysFormer with the rPPG-Toolbox protocol, so results compare with its published
tables (Liu et al., NeurIPS 2023, Table 7).

Protocol (configs/train_configs/PURE_PURE_UBFC-rPPG_PHYSFORMER_BASIC.yaml and PhysFormerTrainer.py):
  train set = first 80% of the training dataset's subjects, validation = the other 20% (split by subject here; the
  toolbox splits its sorted file list, which for PURE / UBFC is almost the same); 160-frame chunks, DiffNormalized
  input and label, batch 4, Adam lr 1e-4, weight decay 5e-5, 10 epochs, loss = NegPearson + (frequency CE + label
  distribution KL) with weights 1 / 1 (the toolbox schedule for epochs <= 10; losses ported in
  bench/toolbox_loss.py because rppg1/losses.py feeds un-normalised power to the cross-entropy), best epoch by
  validation HR RMSE,
  test = every video of the test dataset, HR by FFT over the whole video (bench/metrics.py).
Deviations, reported in the results: the model is rppg1/model/physformer.py (its conv stem is 96 channels wide in
all three layers, the official code uses dim/4, dim/2, dim; no dropout), and mixed precision (fp16) is used so it
fits a 6 GB GPU.

    python -m bench.run pos   --test ubfc                                   (from rppg1/)
    python -m bench.run train --train pure --test ubfc [--epochs 10 --batch 1 --accum 4 --name PURE_UBFC]
    python -m bench.run train --train mcd_IriunWebcam --test mcd_IriunWebcam   (last 20% of subjects held out)
    python -m bench.run test  --ckpt runs/PURE_UBFC/best.pt --test pure
    python -m bench.run report

--arch cvprlab:<preset> trains the CVPR Lab unified model (../cvprlab, presets phase1_physformer ... edge) under the
same split, input, label and test protocol; it also gets the STMap of each chunk, its own curriculum loss
(cvprlab/losses.py), and every clip's frame rate. --valid video (default) picks the best epoch by whole-video HR
RMSE on the validation subjects, the same estimator as the test; --valid chunk is the older per-chunk Welch HR.
"""
import argparse
import glob
import json
import math
import os
import sys
import time

import numpy as np
import torch
from scipy.signal import welch
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.metrics import codec_notch, post_process, summary, video_hr                 # noqa: E402
from bench.preprocess import CACHE, ROOT                                    # noqa: E402
from bench.toolbox_loss import physformer_loss                              # noqa: E402
from model import PhysFormer                                                # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "cvprlab"))
from cvprlab import CVPRLab, CVPRLabConfig, preset as cvprlab_preset        # noqa: E402
from cvprlab.data.stmap import build_stmap                                  # noqa: E402
from cvprlab.losses import cvprlab_loss                                     # noqa: E402

RUNS = os.path.join(ROOT, "runs")
T = 160
PUBLISHED = {   # rPPG-Toolbox Table 7 (MAE, RMSE, MAPE, Pearson, SNR)
    ("PhysFormer", "PURE", "UBFC-rPPG"): (1.44, 3.77, 1.66, 0.98, 0.18),
    ("PhysFormer", "UBFC-rPPG", "PURE"): (12.92, 24.36, 23.92, 0.47, 2.16),
    ("PhysFormer", "SCAMPS", "UBFC-rPPG"): (4.56, 10.48, 5.18, 0.81, -6.34),
    ("POS", "-", "UBFC-rPPG"): (4.08, 7.72, 3.93, 0.92, -2.39),
    ("POS", "-", "PURE"): (3.67, 11.82, 7.25, 0.88, 6.87),
    ("CHROM", "-", "UBFC-rPPG"): (4.06, 8.83, 3.84, 0.89, -2.96),
    ("CHROM", "-", "PURE"): (5.77, 14.93, 11.52, 0.81, 4.58),
}


def load_metas(name):
    d = os.path.join(CACHE, name)
    metas = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(d, "*.json")))]
    if not metas:
        raise SystemExit(f"no preprocessed videos in {d}: run python -m bench.preprocess first")
    for m in metas:
        m["dir"] = d
    return metas


def split_by_subject(metas, frac):
    subs = sorted({m["subject"] for m in metas})
    cut = int(round(len(subs) * frac))
    tr = set(subs[:cut])
    return [m for m in metas if m["subject"] in tr], [m for m in metas if m["subject"] not in tr]


class Chunks(Dataset):
    """Non-overlapping 160-frame chunks (the remainder of each video is dropped, as in the toolbox)."""

    def __init__(self, metas, augment=False, stmap=False):
        self.metas, self.augment, self.stmap, self._mm = metas, augment, stmap, {}
        self.index = [(i, k) for i, m in enumerate(metas) for k in range(m["n_frames"] // T)]

    def __len__(self):
        return len(self.index)

    def frames(self, i):
        if i not in self._mm:
            m = self.metas[i]
            self._mm[i] = np.load(os.path.join(m["dir"], m["video_id"] + ".frames.npy"), mmap_mode="r")
        return self._mm[i]

    def __getitem__(self, j):
        i, k = self.index[j]
        m, s = self.metas[i], k * T
        f = np.asarray(self.frames(i)[s:s + T + 1], dtype=np.float32)
        d = (f[1:] - f[:-1]) / (f[1:] + f[:-1] + 1e-7) / m["frame_diff_std"]
        if len(d) < T:                                     # last frame of the video: the toolbox appends a zero frame
            d = np.concatenate([d, np.zeros((T - len(d),) + d.shape[1:], np.float32)])
        flip = self.augment and np.random.rand() < 0.5
        if flip:
            d = d[:, :, ::-1]
        x = torch.from_numpy(np.ascontiguousarray(d.transpose(3, 0, 1, 2)))
        st = torch.zeros(0)
        if self.stmap:
            raw = f[:T] if len(f) > T else np.concatenate([f, np.repeat(f[-1:], T - len(f), 0)])
            st = torch.from_numpy(build_stmap(raw[:, :, ::-1] if flip else raw))
        y = torch.tensor(m["label_diffnorm"][s:s + T], dtype=torch.float32)
        return x, st, y, i, k, m["fps"]


def label_hr(y, fs):
    """rPPG-Toolbox PhysFormerTrainer.get_hr: Welch peak in 30-180 bpm."""
    p, q = welch(y, fs, nfft=int(1e5 / fs), nperseg=min(len(y) - 1, 256))
    m = (p > 0.5) & (p < 3.0)
    return float(p[m][np.argmax(q[m])] * 60)


def zscore(x):
    return (x - x.mean(dim=-1, keepdim=True)) / (x.std(dim=-1, keepdim=True) + 1e-8)


def build_model(arch="rppg1"):
    if arch == "rppg1":
        return PhysFormer(dim=96, ff_hidden=144, depth=12, heads=4, theta=0.7, tau=2.0, tube_size=(4, 4, 4), frames=T)
    if arch.startswith("cvprlab:"):                      # cvprlab:<preset>[,key=value...], e.g. ,eta=1.0
        name, *kv = arch.split(":", 1)[1].split(",")
        cast = lambda k, v: v.lower() in ("1", "true") if isinstance(getattr(CVPRLabConfig, k), bool) \
            else type(getattr(CVPRLabConfig, k))(v)
        over = {k: cast(k, v) for k, v in (s.split("=") for s in kv)}
        return CVPRLab(cvprlab_preset(name, frames=T, **over))
    raise SystemExit(f"unknown --arch {arch}")


def method_name(arch):
    return "PhysFormer (rppg1)" if arch == "rppg1" else f"CVPR Lab {arch.split(':', 1)[1]}"


def needs_stmap(model):
    return isinstance(model, CVPRLab) and model.cfg.use_stmap


def run_model(model, x, st, fs, device):
    if isinstance(model, CVPRLab):
        return model(x, st.to(device, non_blocking=True) if st.numel() else None, fs.float().to(device))
    return model(x)


def loader(ds, batch, shuffle, workers):
    return DataLoader(ds, batch_size=batch, shuffle=shuffle, num_workers=workers, pin_memory=True,
                      persistent_workers=workers > 0, drop_last=False)


@torch.no_grad()
def predict(model, ds, batch, workers, device):
    """Per-video concatenated chunk predictions and labels."""
    model.eval()
    out = {}
    for x, st, y, i, k, fs in loader(ds, batch, False, workers):
        with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            p = run_model(model, x.to(device, non_blocking=True), st, fs, device)
        for pp, yy, ii, kk in zip(p.float().cpu().numpy(), y.numpy(), i.tolist(), k.tolist()):
            out.setdefault(ii, {})[kk] = (pp, yy)
    return {i: (np.concatenate([v[k][0] for k in sorted(v)]), np.concatenate([v[k][1] for k in sorted(v)]))
            for i, v in out.items()}


def evaluate(model, metas, batch, workers, device):
    preds = predict(model, Chunks(metas, stmap=needs_stmap(model)), batch, workers, device)
    rows = []
    for i, (p, y) in preds.items():
        hp, hl, snr = video_hr(p, y, metas[i]["fps"], diff_flag=True, notch=codec_notch(metas[i]))
        rows.append({"video": metas[i]["video_id"], "subject": metas[i]["subject"], "hr_pred": hp, "hr_label": hl,
                     "snr": snr})
    return summary([r["hr_pred"] for r in rows], [r["hr_label"] for r in rows], [r["snr"] for r in rows]), rows


def valid_rmse(model, ds, batch, workers, device, mode="video"):
    if mode == "video":                                  # same whole-video estimator as the test
        return evaluate(model, ds.metas, batch, workers, device)[0]["RMSE"]
    model.eval()
    errs = []
    with torch.no_grad():
        for x, st, y, i, k, fs in loader(ds, batch, False, workers):
            with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                p = zscore(run_model(model, x.to(device), st, fs, device).float()).cpu().numpy()
            errs += [(label_hr(pp, float(f)) - label_hr(yy, float(f))) ** 2 for pp, yy, f in zip(p, y.numpy(), fs)]
    return float(np.sqrt(np.mean(errs)))


def train(a):
    torch.manual_seed(a.seed), np.random.seed(a.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tr_all = load_metas(a.train)
    if a.test == a.train:                               # intra-dataset: last holdout_frac of subjects = test
        tr_all, test = split_by_subject(tr_all, 1 - a.holdout_frac)
    else:
        test = load_metas(a.test) if a.test else []
    tr, va = split_by_subject(tr_all, a.train_frac) if a.train_frac < 1 else (tr_all, [])
    if test and not a.allow_overlap and test[0]["dataset"] == tr_all[0]["dataset"]:
        overlap = {m["subject"] for m in tr_all} & {m["subject"] for m in test}
        if overlap:
            raise SystemExit(f"test subjects {sorted(overlap)} are also in training (use another dataset, or "
                             "--allow-overlap for a smoke test only)")
    run = os.path.join(RUNS, a.name)
    os.makedirs(run, exist_ok=True)
    log = open(os.path.join(run, "train.log"), "a")
    say = lambda s: (print(s, flush=True), log.write(s + "\n"), log.flush())
    say(f"train {a.train}: {len(tr)} videos / {len({m['subject'] for m in tr})} subjects; valid {len(va)} videos / "
        f"{len({m['subject'] for m in va})} subjects; test {a.test}: {len(test)} videos; device {device}")
    model = build_model(a.arch).to(device)
    cvl = isinstance(model, CVPRLab)
    say(f"arch {a.arch}: {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M parameters; valid by {a.valid}")
    opt = torch.optim.Adam(model.parameters(), lr=a.lr, weight_decay=5e-5)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=50, gamma=0.5)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    start, best = 1, {"rmse": None, "epoch": None}
    state_p = os.path.join(run, "state.json")
    if os.path.isfile(state_p):                           # resume
        st = json.load(open(state_p))
        ck = torch.load(os.path.join(run, f"epoch{st['epoch']}.pt"), map_location=device)
        model.load_state_dict(ck["model"]), opt.load_state_dict(ck["opt"]), sched.load_state_dict(ck["sched"])
        start, best = st["epoch"] + 1, st["best"]
        say(f"resumed after epoch {st['epoch']}")
    ds = Chunks(tr, augment=a.augment, stmap=needs_stmap(model))
    dl = loader(ds, a.batch, True, a.workers)
    vds = Chunks(va, stmap=needs_stmap(model)) if va else None
    for epoch in range(start, a.epochs + 1):
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        opt.zero_grad(set_to_none=True)
        for step, (x, st, y, i, k, fs) in enumerate(dl, 1):
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            hr = torch.tensor([label_hr(yy, float(f)) for yy, f in zip(y.cpu().numpy(), fs)], device=device)
            with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                out = run_model(model, x, st, fs, device) if not (cvl and model.diffusion is not None) else \
                    model(x, st.to(device) if st.numel() else None, fs.float().to(device), return_features=True)
            p, feats = out if isinstance(out, tuple) else (out, None)
            p = zscore(p.float())
            if cvl:
                loss, parts = cvprlab_loss(p, y, hr, fs.float().to(device), epoch, a.epochs, model.cfg)
                if feats is not None:                    # diffusion refiner: noise-prediction loss on the label
                    loss = loss + model.diffusion.loss(feats.float(), p.detach(), zscore(y))
            else:
                loss, parts = 0.0, {}
                for f in fs.unique().tolist():           # one loss per frame rate (mixed-fps training)
                    sel = (fs == f).to(device)
                    l, parts = physformer_loss(p[sel], y[sel], hr[sel], float(f))
                    loss = loss + l * sel.sum() / len(fs)
            scaler.scale(loss / a.accum).backward()      # gradient accumulation: effective batch = batch x accum
            if step % a.accum == 0 or step == len(dl):
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            tot, n = tot + float(loss), n + 1
            mae_sum = (mae_sum if step > 1 else 0.0) + parts["train_hr_mae"]
            if step % 100 == 0:
                say(f"epoch {epoch} step {step}/{len(dl)} loss {tot / n:.4f} train HR MAE {mae_sum / step:.2f} "
                    f"({time.time() - t0:.0f}s)")
        sched.step()
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict()},
                   os.path.join(run, f"epoch{epoch}.pt"))
        msg = f"epoch {epoch}: train loss {tot / max(n, 1):.4f} ({time.time() - t0:.0f}s)"
        if vds:
            rmse = valid_rmse(model, vds, a.batch, a.workers, device, a.valid)
            msg += f", valid HR RMSE {rmse:.2f}"
            if best["rmse"] is None or rmse < best["rmse"]:
                best = {"rmse": rmse, "epoch": epoch}
                torch.save({"model": model.state_dict()}, os.path.join(run, "best.pt"))
        else:
            best = {"rmse": None, "epoch": epoch}
            torch.save({"model": model.state_dict()}, os.path.join(run, "best.pt"))
        json.dump({"epoch": epoch, "best": best}, open(state_p, "w"))
        say(msg)
    say(f"best epoch {best['epoch']} (valid RMSE {best['rmse']})")
    if test:
        model.load_state_dict(torch.load(os.path.join(run, "best.pt"), map_location=device)["model"])
        res, rows = evaluate(model, test, a.batch, a.workers, device)
        save_result(a.name, method_name(a.arch), tr_all[0]["dataset"], test[0]["dataset"], res, rows,
                    {"arch": a.arch, "epochs": a.epochs, "best_epoch": best["epoch"], "best_valid_rmse": best["rmse"],
                     "valid": a.valid, "batch": a.batch, "accum": a.accum, "train_videos": len(tr),
                     "valid_videos": len(va), "amp": device.type == "cuda",
                     "params": sum(p.numel() for p in model.parameters())})
        say(f"TEST {test[0]['dataset']}: " + json.dumps({k: round(v, 3) for k, v in res.items()}))


def test(a):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(a.arch).to(device)
    model.load_state_dict(torch.load(a.ckpt, map_location=device)["model"])
    metas = load_metas(a.test)
    res, rows = evaluate(model, metas, a.batch, a.workers, device)
    save_result(a.name or f"test_{a.test}", method_name(a.arch), a.train_label or "?", metas[0]["dataset"], res,
                rows, {"ckpt": a.ckpt, "arch": a.arch})
    print(json.dumps(res, indent=1))


def pos_wang(rgb, fs):
    """POS (Wang et al. 2017) as in rPPG-Toolbox unsupervised_methods/methods/POS_WANG.py."""
    rgb = np.asarray(rgb, dtype=np.float64)
    n, l = len(rgb), math.ceil(1.6 * fs)
    h = np.zeros(n)
    proj = np.array([[0, 1, -1], [-2, 1, 1]])
    for t in range(l, n + 1):
        c = rgb[t - l:t] / rgb[t - l:t].mean(axis=0)
        s = proj @ c.T
        p = s[0] + s[1] * (s[0].std() / (s[1].std() + 1e-12))
        h[t - l:t] += p - p.mean()
    return h


def chrom(rgb, fs):
    """CHROM (de Haan & Jeanne 2013), whole-signal version with the toolbox's band-pass."""
    from scipy import signal as sps
    rn = np.asarray(rgb, np.float64) / np.asarray(rgb, np.float64).mean(axis=0)
    xs, ys = 3 * rn[:, 0] - 2 * rn[:, 1], 1.5 * rn[:, 0] + rn[:, 1] - 1.5 * rn[:, 2]
    b, a_ = sps.butter(3, [0.7 / fs * 2, 2.5 / fs * 2], btype="bandpass")
    xf, yf = sps.filtfilt(b, a_, xs), sps.filtfilt(b, a_, ys)
    return xf - (xf.std() / yf.std()) * yf


def unsupervised(a):
    metas = load_metas(a.test)
    for name, fn in (("POS", pos_wang), ("CHROM", chrom)):
        rows = []
        for m in metas:
            bvp = fn(m["rgb_mean"], m["fps"])
            hp, hl, snr = video_hr(bvp, np.asarray(m["ppg"]), m["fps"], diff_flag=False, notch=codec_notch(m))
            rows.append({"video": m["video_id"], "subject": m["subject"], "hr_pred": hp, "hr_label": hl, "snr": snr})
        res = summary([r["hr_pred"] for r in rows], [r["hr_label"] for r in rows], [r["snr"] for r in rows])
        save_result(f"{name}_{a.test}", name, "-", metas[0]["dataset"], res, rows, {})
        print(name, metas[0]["dataset"], json.dumps({k: round(v, 3) for k, v in res.items()}))


def save_result(name, method, train_set, test_set, res, rows, info):
    os.makedirs(os.path.join(RUNS, "results"), exist_ok=True)
    json.dump({"method": method, "train": train_set, "test": test_set, "metrics": res, "per_video": rows,
               "info": info}, open(os.path.join(RUNS, "results", name + ".json"), "w"), indent=1)


def report(a):
    rows = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(RUNS, "results", "*.json")))]
    f = lambda m, k: f"{m[k]:.2f} ± {m[k + '_se']:.2f}"
    L = ["# rPPG benchmark: rppg1 PhysFormer vs rPPG-Toolbox (Liu et al., NeurIPS 2023)", "",
         "Video-level HR (FFT over the whole video), toolbox protocol (bench/run.py). Published = rPPG-Toolbox "
         "Table 7. ± = standard error.", "",
         "| Method | Train | Test | n videos | MAE ↓ | RMSE ↓ | MAPE % ↓ | Pearson ↑ | SNR dB ↑ | within 5 bpm |"
         " Published MAE / RMSE / MAPE / r / SNR |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        m = r["metrics"]
        key = (r["method"].split(" ")[0], r["train"], r["test"])
        pub = PUBLISHED.get(key)
        L.append(f"| {r['method']} | {r['train']} | {r['test']} | {m['n_videos']} | {f(m, 'MAE')} | {f(m, 'RMSE')} |"
                 f" {f(m, 'MAPE')} | {m['Pearson']:.2f} | {f(m, 'SNR')} | {m['within_5bpm']:.0%} | "
                 + (" / ".join(map(str, pub)) if pub else "—") + " |")
    L += ["", "Published rows without our counterpart yet:", ""]
    have = {(r["method"].split(" ")[0], r["train"], r["test"]) for r in rows}
    L += [f"- {k[0]} trained on {k[1]}, tested on {k[2]}: MAE {v[0]}, RMSE {v[1]}, MAPE {v[2]}, r {v[3]}"
          for k, v in PUBLISHED.items() if k not in have]
    L += ["", "Deviations from the toolbox: rppg1's PhysFormer stem is 96 channels wide in all three conv layers "
          "(official: 24 / 48 / 96) and has no dropout; frequency losses from the toolbox (bench/toolbox_loss.py; "
          "rppg1/losses.py uses un-normalised power); fp16 mixed precision; batch 4 = 1 clip x 4 accumulated "
          "steps (6 GB GPU); validation split by subject."]
    p = os.path.join(RUNS, "REPORT.md")
    open(p, "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--train", required=True, help="cache name, e.g. pure, ubfc, mcd_IriunWebcam")
    t.add_argument("--test")
    t.add_argument("--name")
    t.add_argument("--epochs", type=int, default=10)
    t.add_argument("--batch", type=int, default=1, help="clips per GPU step (4 needs ~9 GB; 1 fits 6 GB)")
    t.add_argument("--accum", type=int, default=4, help="gradient accumulation steps (toolbox batch 4 = 1 x 4)")
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--train-frac", type=float, default=0.8, help="share of subjects for training, rest = validation")
    t.add_argument("--holdout-frac", type=float, default=0.2,
                   help="when --test equals --train: share of subjects (the last ones) held out as the test set")
    t.add_argument("--workers", type=int, default=4)
    t.add_argument("--augment", action="store_true", help="random horizontal flip (off in the toolbox config)")
    t.add_argument("--allow-overlap", action="store_true", help="smoke tests only: allow test subjects in training")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--arch", default="rppg1", help="rppg1, or cvprlab:<preset> e.g. cvprlab:phase4_frequency")
    t.add_argument("--valid", choices=["video", "chunk"], default="video", help="best-epoch criterion")
    e = sub.add_parser("test")
    e.add_argument("--arch", default="rppg1")
    e.add_argument("--ckpt", required=True)
    e.add_argument("--test", required=True)
    e.add_argument("--train-label")
    e.add_argument("--name")
    e.add_argument("--batch", type=int, default=4)
    e.add_argument("--workers", type=int, default=2)
    u = sub.add_parser("pos")
    u.add_argument("--test", required=True)
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "train":
        a.name = a.name or f"{a.train}_{a.test or 'none'}"
    {"train": train, "test": test, "pos": unsupervised, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
