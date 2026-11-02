"""L = NegPearson + beta(epoch) * (lambda1 * L_freqCE + lambda2 * L_LD),  beta(epoch) = beta0 * eta^((epoch-1)/epochs)

NegPearson matches waveform shape (rPPG has no absolute units). Frequency CE treats the normalised band power at
40..179 bpm as class scores and pushes the peak onto the true rate; label distribution learning replaces the one-hot
target with a Gaussian over neighbouring rates. The time term is trusted first; the frequency terms phase in.
Spectral terms follow rPPG-Toolbox's PhysFormer loss (Hann-windowed DFT at each whole bpm, normalised to sum 1).
"""
import math

import torch
import torch.nn.functional as F

BPM = torch.arange(40, 180, dtype=torch.float32)


def normalised_power(x, fs):
    """x (B,N), fs (B,) or float -> (B,140) power at 40..179 bpm, rows summing to 1."""
    b, n = x.shape
    fs = torch.as_tensor(fs, dtype=torch.float32, device=x.device).reshape(-1, 1).expand(b, 1)
    t = torch.arange(n, dtype=torch.float32, device=x.device)
    f = BPM.to(x.device)[None, :] / 60.0                                   # (1,140) Hz
    ang = 2 * math.pi * f[:, :, None] * t[None, None, :] / fs[:, :, None]   # (B,140,N)
    xw = (x * torch.hann_window(n, periodic=False, device=x.device)[None, :])[:, None, :]
    p = (xw * torch.sin(ang)).sum(-1) ** 2 + (xw * torch.cos(ang)).sum(-1) ** 2
    return p / p.sum(dim=1, keepdim=True)


def gaussian_target(hr, std=1.0):
    mu = hr.floor()[:, None]
    g = torch.exp(-(BPM.to(hr.device)[None, :] - mu) ** 2 / (2 * std ** 2)) / (math.sqrt(2 * math.pi) * std)
    return g.clamp_min(1e-15)


def neg_pearson(p, y):
    p, y = p - p.mean(dim=1, keepdim=True), y - y.mean(dim=1, keepdim=True)
    return (1 - (p * y).sum(1) / torch.sqrt((p ** 2).sum(1) * (y ** 2).sum(1) + 1e-8)).mean()


def curriculum_beta(epoch, epochs, beta0=1.0, eta=5.0):
    return beta0 * eta ** ((epoch - 1) / max(epochs, 1))


def cvprlab_loss(p, y, hr, fs, epoch, epochs, cfg):
    """p: z-scored prediction (B,N); y: label (B,N); hr: label bpm (B,); fs: (B,) -> (loss, parts)."""
    power = normalised_power(p.float(), fs)
    ce = F.cross_entropy(power, (hr.floor() - 40).clamp(0, 139).long())
    g = gaussian_target(hr)
    ld = (g * (g.log() - F.softmax(power, dim=1).log())).sum(1).div(140).mean()
    pear = neg_pearson(p, y)
    beta = curriculum_beta(epoch, epochs, cfg.beta0, cfg.eta)
    mae = (BPM.to(p.device)[power.argmax(1)] - hr).abs().mean()
    return pear + beta * (cfg.lambda_ce * ce + cfg.lambda_ld * ld), {
        "neg_pearson": pear.item(), "ce": ce.item(), "ld": ld.item(), "beta": beta, "train_hr_mae": mae.item()}
