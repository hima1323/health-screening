"""PhysFormer frequency losses exactly as rPPG-Toolbox neural_methods/loss/PhysFormerLossComputer.py
(cross_entropy_power_spectrum_DLDL_softmax2), vectorised over the batch.

The power at each whole bpm from 40 to 179 is a Hann-windowed DFT at that exact frequency, normalised to sum to 1
("analogous softmax"); frequency loss = cross-entropy of those 140 values against the true bpm; distribution loss =
KL(softmax(power) || Gaussian(true bpm, std 1)) averaged over the 140 bins.

Why not rppg1/losses.py: there the raw (un-normalised) power is used as the cross-entropy logits. For a z-scored
160-sample signal those values are in the thousands, so the loss is ~3000 and the gradients explode (seen in the
smoke test). Total loss = NegPearson + (frequency CE + KL), the toolbox weights for epochs <= 10.
"""
import math

import numpy as np
import torch
import torch.nn.functional as F

BPM = torch.arange(40, 180, dtype=torch.float32)          # 140 bins


def normalised_power(x, fs):
    """x: (B, N) -> (B, 140) power at 40..179 bpm, each row summing to 1."""
    b, n = x.shape
    t = torch.arange(n, dtype=torch.float32, device=x.device)
    k = (BPM.to(x.device) / 60.0) / (fs / n)                 # DFT bin index of each bpm (fractional)
    ang = 2 * math.pi * k[:, None] * t[None, :] / n          # (140, N)
    xw = x * torch.hann_window(n, periodic=False, device=x.device)[None, :]
    p = (xw @ torch.sin(ang).T) ** 2 + (xw @ torch.cos(ang).T) ** 2
    return p / p.sum(dim=1, keepdim=True)


def gaussian_target(hr, std=1.0):
    """(B,) bpm -> (B, 140) N(int(hr), std) sampled at 40..179, floored at 1e-15 (toolbox normal_sampling)."""
    mu = hr.floor()[:, None]
    g = torch.exp(-(BPM.to(hr.device)[None, :] - mu) ** 2 / (2 * std ** 2)) / (math.sqrt(2 * math.pi) * std)
    return g.clamp_min(1e-15)


def neg_pearson(p, y):
    p, y = p - p.mean(dim=1, keepdim=True), y - y.mean(dim=1, keepdim=True)
    r = (p * y).sum(1) / torch.sqrt((p ** 2).sum(1) * (y ** 2).sum(1) + 1e-8)
    return (1 - r).mean()


def physformer_loss(p, y, hr, fs, a=1.0, b=1.0):
    """p: z-scored prediction (B, N); y: label (B, N); hr: label bpm (B,). -> (loss, parts)."""
    power = normalised_power(p, fs)
    target = (hr.floor() - 40).clamp(0, 139).long()
    ce = F.cross_entropy(power, target)
    q = F.softmax(power, dim=1)
    kl = (gaussian_target(hr) * (gaussian_target(hr).log() - q.log())).sum(1).div(140).mean()
    pear = neg_pearson(p, y)
    mae = (BPM.to(p.device)[power.argmax(1)] - hr).abs().mean()
    return a * pear + b * (ce + kl), {"neg_pearson": pear.item(), "ce": ce.item(), "kl": kl.item(),
                                      "train_hr_mae": mae.item()}
