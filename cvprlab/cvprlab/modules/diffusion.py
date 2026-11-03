"""(9b) Frequency-conditioned diffusion refiner (FreqPhys).

A DDPM over the waveform that refines the deterministic estimate rather than replacing it: every reverse step is
conditioned on the frequency-denoised features and on the estimate itself. Trained on the full K-step schedule,
sampled with deterministic DDIM (default 20 steps), since K reverse steps per clip is offline-only.
"""
import math

import torch
import torch.nn as nn
import torch.nn.functional as F


def timestep_embedding(t, dim):
    half = dim // 2
    f = torch.exp(-math.log(10000) * torch.arange(half, device=t.device, dtype=torch.float32) / half)
    a = t.float()[:, None] * f[None, :]
    return torch.cat([a.sin(), a.cos()], -1)


class Denoiser(nn.Module):
    def __init__(self, cond_dim, hidden=64, layers=6):
        super().__init__()
        self.inp = nn.Conv1d(2 + cond_dim, hidden, 1)
        self.temb = nn.Sequential(nn.Linear(hidden, hidden), nn.SiLU(), nn.Linear(hidden, hidden))
        self.convs = nn.ModuleList([nn.Conv1d(hidden, hidden, 3, padding=2 ** (i % 4), dilation=2 ** (i % 4))
                                    for i in range(layers)])
        self.out = nn.Conv1d(hidden, 1, 1)
        self.hidden = hidden

    def forward(self, y_t, y_est, cond, t):
        h = self.inp(torch.cat([y_t[:, None], y_est[:, None], cond], 1))
        e = self.temb(timestep_embedding(t, self.hidden))[:, :, None]
        for conv in self.convs:
            h = h + conv(F.silu(h + e))
        return self.out(h).squeeze(1)


class FreqDiffusion(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.k, self.steps = cfg.diffusion_steps, cfg.ddim_steps
        betas = torch.linspace(1e-4, 0.02, self.k)
        self.register_buffer("abar", torch.cumprod(1 - betas, 0), persistent=False)
        self.net = Denoiser(cfg.dim)

    def loss(self, cond, y_est, y0):
        """Noise-prediction MSE for a random step; y0 is the (z-scored) reference waveform."""
        t = torch.randint(0, self.k, (y0.shape[0],), device=y0.device)
        a = self.abar[t][:, None]
        eps = torch.randn_like(y0)
        return F.mse_loss(self.net(a.sqrt() * y0 + (1 - a).sqrt() * eps, y_est, cond, t), eps)

    @torch.no_grad()
    def sample(self, cond, y_est):
        ts = torch.linspace(self.k - 1, 0, self.steps, device=cond.device).long()
        y = torch.randn_like(y_est)
        for i, t in enumerate(ts):
            a = self.abar[t]
            eps = self.net(y, y_est, cond, t.expand(y.shape[0]))
            y0 = (y - (1 - a).sqrt() * eps) / a.sqrt()
            a_prev = self.abar[ts[i + 1]] if i + 1 < len(ts) else torch.tensor(1.0, device=cond.device)
            y = a_prev.sqrt() * y0 + (1 - a_prev).sqrt() * eps
        return y
