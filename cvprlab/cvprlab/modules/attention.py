"""Attention written out explicitly (no nn.MultiheadAttention: its fused fast path cannot be decomposed by
torch.export, which is what keeps ONNX export possible)."""
import torch.nn as nn


def attend(q, k, v, heads, scale, bias=None):
    """q (B,N,D), k/v (B,M,D) -> (B,N,D); bias broadcastable to (B,heads,N,M) is added to the logits."""
    b, n, d = q.shape
    m = k.shape[1]
    q = q.reshape(b, n, heads, d // heads).transpose(1, 2)
    k = k.reshape(b, m, heads, d // heads).transpose(1, 2)
    v = v.reshape(b, m, heads, d // heads).transpose(1, 2)
    logits = (q @ k.transpose(-2, -1)) * scale
    if bias is not None:
        logits = logits + bias
    return (logits.softmax(dim=-1) @ v).transpose(1, 2).reshape(b, n, d)


class CrossAttention(nn.Module):
    """Pre-norm cross-attention block with a feed-forward: x <- x + Attn(LN x, LN ctx); x <- x + FF(LN x)."""

    def __init__(self, dim, heads=4, ctx_dim=None, ff_mult=2):
        super().__init__()
        ctx_dim = ctx_dim or dim
        self.heads, self.scale = heads, (dim // heads) ** -0.5
        self.nq, self.nc = nn.LayerNorm(dim), nn.LayerNorm(ctx_dim)
        self.q, self.k, self.v = nn.Linear(dim, dim), nn.Linear(ctx_dim, dim), nn.Linear(ctx_dim, dim)
        self.o = nn.Linear(dim, dim)
        self.ff = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, dim * ff_mult), nn.GELU(),
                                nn.Linear(dim * ff_mult, dim))

    def forward(self, x, ctx, bias=None):
        c = self.nc(ctx)
        x = x + self.o(attend(self.q(self.nq(x)), self.k(c), self.v(c), self.heads, self.scale, bias))
        return x + self.ff(x)


def fold_time(x):
    """(B,C,T,P) -> (B*T,P,C)"""
    b, c, t, p = x.shape
    return x.permute(0, 2, 3, 1).reshape(b * t, p, c)


def unfold_time(x, b):
    """(B*T,P,C) -> (B,C,T,P)"""
    bt, p, c = x.shape
    return x.reshape(b, bt // b, p, c).permute(0, 3, 1, 2)


