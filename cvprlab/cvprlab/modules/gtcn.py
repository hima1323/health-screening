"""(8) Physics-grounded gated TCN (PHASE-Net).

Beer-Lambert + vessel compliance -> intensity change ~ pressure pulsation z(t); linearised Navier-Stokes observed at
one point -> damped oscillator z'' + a z' + w^2 z = u(t); discretised -> an LTI state-space model whose solution is a
causal convolution of the drive u, which a finite dilated causal TCN approximates. Hence: causal (left padding only),
dilated 1, 2, 4, ..., WaveNet gating tanh(Wf*x) * sigmoid(Wg*x), residual and skip connections. Six layers of
kernel 3 see 127 samples (4.2 s at 30 fps). Causality also makes streaming inference possible.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class GatedLayer(nn.Module):
    def __init__(self, dim, kernel, dilation):
        super().__init__()
        self.pad = (kernel - 1) * dilation
        self.filt = nn.Conv1d(dim, dim, kernel, dilation=dilation)
        self.gate = nn.Conv1d(dim, dim, kernel, dilation=dilation)
        self.res, self.skip = nn.Conv1d(dim, dim, 1), nn.Conv1d(dim, dim, 1)

    def forward(self, x):
        h = F.pad(x, (self.pad, 0))
        h = torch.tanh(self.filt(h)) * torch.sigmoid(self.gate(h))
        return x + self.res(h), self.skip(h)


class GTCN(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.layers = nn.ModuleList([GatedLayer(cfg.dim, cfg.gtcn_kernel, 2 ** i) for i in range(cfg.gtcn_layers)])
        self.out = nn.Sequential(nn.GELU(), nn.Conv1d(cfg.dim, cfg.dim, 1))

    @property
    def receptive_field(self):
        return 1 + sum(l.pad for l in self.layers)

    def forward(self, x):
        skips = 0
        for layer in self.layers:
            x, s = layer(x)
            skips = skips + s
        return x + self.out(skips)
