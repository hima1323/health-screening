"""(3b) Pixel difference convolutions for the STMap branch (PhysNeXt SDMU).

Central-PDC: conv(x) - (sum of kernel weights) * x[centre] - change relative to the local centre in all directions.
Ring-PDC:    sum_i w_i * (x[p_i] - x[p_{i+1}]) over the 8-neighbour ring - angular differences. Its effective kernel
             sums to zero by construction, so it is blind to any constant offset, i.e. to slow illumination drift.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

RING = [0, 1, 2, 5, 8, 7, 6, 3]   # flat 3x3 indices of the 8 neighbours, clockwise from top-left


class CentralPDC(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.conv = nn.Conv2d(cin, cout, 3, padding=1, bias=False)

    def forward(self, x):
        return self.conv(x) - F.conv2d(x, self.conv.weight.sum(dim=(2, 3), keepdim=True))


class RingPDC(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.w = nn.Parameter(torch.randn(cout, cin, 8) * (2.0 / (cin * 8)) ** 0.5)
        m = torch.zeros(8, 9)                    # weight i -> +1 at ring[i], -1 at ring[i+1]
        for i in range(8):
            m[i, RING[i]] += 1
            m[i, RING[(i + 1) % 8]] -= 1
        self.register_buffer("m", m, persistent=False)

    def kernel(self):
        return (self.w @ self.m).reshape(*self.w.shape[:2], 3, 3)

    def forward(self, x):
        return F.conv2d(x, self.kernel(), padding=1)


class SDMUBlock(nn.Module):
    """vanilla 3x3 | Central-PDC | Ring-PDC in parallel -> 1x1 fuse -> BN -> ReLU, residual."""

    def __init__(self, dim, use_pdc=True):
        super().__init__()
        self.use_pdc = use_pdc
        self.vanilla = nn.Conv2d(dim, dim, 3, padding=1, bias=False)
        if use_pdc:
            self.central, self.ring = CentralPDC(dim, dim), RingPDC(dim, dim)
        self.fuse = nn.Sequential(nn.Conv2d(dim * (3 if use_pdc else 1), dim, 1, bias=False), nn.BatchNorm2d(dim))

    def forward(self, x):
        h = [self.vanilla(x)] + ([self.central(x), self.ring(x)] if self.use_pdc else [])
        return (x + self.fuse(torch.cat(h, 1))).relu()
