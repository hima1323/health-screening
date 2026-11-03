"""(3) Tube tokenizer + Temporal-Difference transformer (PhysFormer), and the SlowFast two-pathway variant
(PhysFormer++).

TD-MHSA: queries and keys come from 3x3x3 temporal difference convolutions, so attention is computed on colour
change rather than appearance; logits are scaled by a temperature tau (2.0) instead of sqrt(d). The feed-forward
puts a depthwise 3x3x3 convolution between its two 1x1x1 layers.
"""
import torch.nn as nn

from cvprlab.modules.attention import CrossAttention, attend
from cvprlab.modules.tdc import TDC


class LayerNorm3d(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.norm = nn.LayerNorm(dim)

    def forward(self, x):
        return self.norm(x.permute(0, 2, 3, 4, 1)).permute(0, 4, 1, 2, 3)


def to_tokens(x):
    """(B,D,T,H,W) -> (B,N,D)"""
    return x.flatten(2).transpose(1, 2)


class TDMHSA(nn.Module):
    def __init__(self, dim, heads, theta, tau):
        super().__init__()
        self.heads, self.tau = heads, tau
        self.q = nn.Sequential(TDC(dim, dim, (3, 3, 3), theta=theta), nn.BatchNorm3d(dim))
        self.k = nn.Sequential(TDC(dim, dim, (3, 3, 3), theta=theta), nn.BatchNorm3d(dim))
        self.v = nn.Conv3d(dim, dim, 1, bias=False)
        self.o = nn.Linear(dim, dim)

    def forward(self, x):
        out = attend(to_tokens(self.q(x)), to_tokens(self.k(x)), to_tokens(self.v(x)), self.heads, 1.0 / self.tau)
        return self.o(out).transpose(1, 2).reshape(x.shape)


class STFF(nn.Module):
    def __init__(self, dim, hidden):
        super().__init__()
        self.net = nn.Sequential(nn.Conv3d(dim, hidden, 1, bias=False), nn.BatchNorm3d(hidden), nn.GELU(),
                                 nn.Conv3d(hidden, hidden, 3, padding=1, groups=hidden, bias=False),
                                 nn.BatchNorm3d(hidden), nn.GELU(), nn.Conv3d(hidden, dim, 1, bias=False))

    def forward(self, x):
        return self.net(x)


class TDBlock(nn.Module):
    def __init__(self, dim, hidden, heads, theta, tau):
        super().__init__()
        self.n1, self.n2 = LayerNorm3d(dim), LayerNorm3d(dim)
        self.attn, self.ff = TDMHSA(dim, heads, theta, tau), STFF(dim, hidden)

    def forward(self, x):
        x = x + self.attn(self.n1(x))
        return x + self.ff(self.n2(x))


class TDTransformer(nn.Module):
    """(B,D,T,H,W) features -> tube tokens -> depth x TD block. Output (B,D,T/ts,H/hs,W/ws)."""

    def __init__(self, cfg):
        super().__init__()
        theta = cfg.theta if cfg.use_tdc else 0.0
        self.tokenize = nn.Conv3d(cfg.dim, cfg.dim, cfg.tube_size, stride=cfg.tube_size)
        self.blocks = nn.Sequential(*[TDBlock(cfg.dim, cfg.ff_hidden, cfg.heads, theta, cfg.tau)
                                      for _ in range(cfg.depth)])

    def forward(self, x):
        return self.blocks(self.tokenize(x))


class SlowFastTransformer(nn.Module):
    """Slow pathway at the tube's temporal stride (long-range periodic trend) and a fast pathway at full frame rate
    with fewer channels (waveform shape); after every layer the slow tokens read the fast ones by cross-attention."""

    def __init__(self, cfg):
        super().__init__()
        theta = cfg.theta if cfg.use_tdc else 0.0
        fd = int(cfg.dim * cfg.fast_dim_ratio)
        ts, hs, ws = cfg.tube_size
        self.tok_slow = nn.Conv3d(cfg.dim, cfg.dim, cfg.tube_size, stride=cfg.tube_size)
        self.tok_fast = nn.Conv3d(cfg.dim, fd, (1, hs, ws), stride=(1, hs, ws))
        self.slow = nn.ModuleList([TDBlock(cfg.dim, cfg.ff_hidden, cfg.heads, theta, cfg.tau)
                                   for _ in range(cfg.depth)])
        self.fast = nn.ModuleList([TDBlock(fd, fd * 3 // 2, max(1, cfg.heads // 2), theta, cfg.tau)
                                   for _ in range(cfg.depth)])
        self.fuse = nn.ModuleList([CrossAttention(cfg.dim, cfg.heads, ctx_dim=fd) for _ in range(cfg.depth)])

    def forward(self, x):
        s, f = self.tok_slow(x), self.tok_fast(x)
        for slow, fast, fuse in zip(self.slow, self.fast, self.fuse):
            s, f = slow(s), fast(f)
            s = fuse(to_tokens(s), to_tokens(f)).transpose(1, 2).reshape(s.shape)
        return s
