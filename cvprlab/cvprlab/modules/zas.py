"""(2) Zero-FLOPs Axial Swapper (PHASE-Net): transpose H and W for a fraction of the channels.

A pure index permutation - no multiply-accumulates, no parameters - that puts distant facial regions (forehead,
cheeks) into each other's convolutional neighbourhood. The other channels are untouched, so nothing is lost, and
applying it twice is the identity.
"""
import torch
import torch.nn as nn


def swapped_channels(c, ratio=0.5, block=1):
    """Indices of the channels to transpose: blocks of `block` channels, spread evenly at the given ratio."""
    nb = c // block
    pick = [j for j in range(nb) if int((j + 1) * ratio) > int(j * ratio)]
    return torch.tensor([j * block + i for j in pick for i in range(block)], dtype=torch.long)


def zas(x, idx):
    if x.shape[-1] != x.shape[-2]:
        raise ValueError("ZAS needs square feature maps")
    out = x.clone()
    out[:, idx] = x[:, idx].transpose(-1, -2)
    return out


class ZAS(nn.Module):
    def __init__(self, channels, ratio=0.5, block=1):
        super().__init__()
        self.register_buffer("idx", swapped_channels(channels, ratio, block), persistent=False)

    def forward(self, x):
        return zas(x, self.idx)
