"""
Training script for PhysFormer, following the recipe in Sec. 4.2:
Adam optimizer, lr=1e-4, weight_decay=5e-5, 25 epochs, batch size 4,
input clips 160x128x128, alpha=0.1, beta in [1,5] exponential curriculum,
sigma=1.0 for label distribution learning.
"""
import argparse
import os

import torch
from torch.utils.data import DataLoader

from dataset import PhysDataset
from losses import PhysFormerLoss
from model import PhysFormer
from utils import signal_to_hr


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=str, required=True)
    p.add_argument("--epochs", type=int, default=25)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--weight-decay", type=float, default=5e-5)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--clip-len", type=int, default=160)
    p.add_argument("--img-size", type=int, default=128)
    p.add_argument("--ckpt-dir", type=str, default="checkpoints")
    p.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--dim", type=int, default=96)
    p.add_argument("--ff-hidden", type=int, default=144)
    p.add_argument("--depth", type=int, default=12)
    p.add_argument("--heads", type=int, default=4)
    p.add_argument("--log-every", type=int, default=1)
    return p.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.ckpt_dir, exist_ok=True)
    device = torch.device(args.device)

    dataset = PhysDataset(args.data_root, clip_len=args.clip_len, img_size=args.img_size)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True,
                         num_workers=0, drop_last=True)

    model = PhysFormer(dim=args.dim, ff_hidden=args.ff_hidden, depth=args.depth, heads=args.heads,
                        theta=0.7, tau=2.0, tube_size=(4, 4, 4),
                        frames=args.clip_len).to(device)

    criterion = PhysFormerLoss(fps=args.fps, low_bpm=42, high_bpm=180, sigma=1.0,
                                alpha=0.1, beta0=1.0, eta=5.0, epoch_total=args.epochs)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    for epoch in range(1, args.epochs + 1):
        model.train()
        running = {}
        for frames, wave, hr in loader:
            frames, wave, hr = frames.to(device), wave.to(device), hr.to(device)

            pred = model(frames)
            loss, logs = criterion(pred, wave, hr, epoch)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            pred_hr = signal_to_hr(pred.detach(), fps=args.fps)
            logs["hr_mae"] = (pred_hr - hr).abs().mean().item()

            for k, v in logs.items():
                running[k] = running.get(k, 0.0) + v

        n = len(loader)
        msg = " ".join(f"{k}={v / n:.4f}" for k, v in running.items())
        if epoch % args.log_every == 0 or epoch == args.epochs:
            print(f"epoch {epoch}/{args.epochs}: {msg}", flush=True)

        torch.save(model.state_dict(), os.path.join(args.ckpt_dir, f"physformer_epoch{epoch}.pt"))
        torch.save(model.state_dict(), os.path.join(args.ckpt_dir, "physformer_last.pt"))


@torch.no_grad()
def evaluate(model, loader, device, fps=30):
    model.eval()
    errs = []
    for frames, wave, hr in loader:
        frames, hr = frames.to(device), hr.to(device)
        pred = model(frames)
        pred_hr = signal_to_hr(pred, fps=fps)
        errs.append((pred_hr - hr).abs())
    errs = torch.cat(errs)
    return errs.mean().item()


if __name__ == "__main__":
    main()
