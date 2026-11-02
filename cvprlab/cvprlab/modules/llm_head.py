"""(9a) PhysLLM-style refinement head: DDS + Text Prototype Guidance + a pluggable language model.

DDS: learnable-decay causal EMA in the time domain (a depthwise convolution with a lambda^k kernel, no Python loop)
     and along the frequency axis of the spectrum, gated against the raw features.
TPG: patch tokens cross-attend to a bank of learned prototypes, turning continuous haemodynamics into tokens a
     language model can read. A statistical-prior token (mean, std, dominant frequency) is always prepended;
     `prompt_embedding` (B,N,llm_dim) is the hook for scene cues (lighting, motion).
The LM defaults to a small transformer stand-in; pass any module (B,N,llm_dim)->(B,N,llm_dim), e.g. a frozen
Hugging Face model wrapper, as `backbone`.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from cvprlab.modules.attention import CrossAttention


def ema_kernel(lam, k):
    """lam (C,) in (0,1) -> causal depthwise kernel (C,1,k), normalised, newest sample last."""
    p = torch.arange(k - 1, -1, -1, device=lam.device, dtype=lam.dtype)
    w = lam[:, None] ** p[None, :]
    return (w / w.sum(-1, keepdim=True))[:, None, :]


class DDS(nn.Module):
    def __init__(self, dim, k=32):
        super().__init__()
        self.k = k
        self.lam_t = nn.Parameter(torch.full((dim,), 1.5))      # sigmoid -> ~0.82
        self.lam_f = nn.Parameter(torch.full((dim,), 0.0))
        self.g = nn.Parameter(torch.zeros(dim, 1))

    def forward(self, x):
        c, t = x.shape[1], x.shape[-1]
        xt = F.conv1d(F.pad(x, (self.k - 1, 0)), ema_kernel(torch.sigmoid(self.lam_t), self.k).to(x.dtype), groups=c)
        with torch.autocast(x.device.type, enabled=False):
            X = torch.fft.rfft(x.float(), dim=-1)
            kf = min(self.k, X.shape[-1])
            ker = ema_kernel(torch.sigmoid(self.lam_f), kf)
            sm = lambda z: F.conv1d(F.pad(z, (kf - 1, 0)), ker, groups=c)
            xf = torch.fft.irfft(torch.complex(sm(X.real), sm(X.imag)), n=t)
        g = torch.sigmoid(self.g)
        return g * 0.5 * (xt + xf.to(x.dtype)) + (1 - g) * x


class StandInLM(nn.Module):
    def __init__(self, dim, layers, heads=4):
        super().__init__()
        self.layers = nn.ModuleList([CrossAttention(dim, heads) for _ in range(layers)])

    def forward(self, h):
        for layer in self.layers:
            h = layer(h, h)
        return h


class LLMHead(nn.Module):
    def __init__(self, cfg, backbone=None):
        super().__init__()
        d, ld = cfg.dim, cfg.llm_dim
        self.patch = cfg.llm_patch
        self.dds = DDS(d)
        self.inp = nn.Linear(d * cfg.llm_patch, ld)
        self.prototypes = nn.Parameter(torch.randn(1, cfg.llm_prototypes, ld) * 0.02)
        self.tpg = CrossAttention(ld, 4)
        self.prior = nn.Linear(3, ld)
        self.lm = backbone or StandInLM(ld, cfg.llm_layers)
        self.out = nn.Linear(ld, d * cfg.llm_patch)

    def forward(self, x, fps, prompt_embedding=None):
        b, c, t = x.shape
        x = self.dds(x)
        n = t // self.patch
        tok = self.inp(x[..., :n * self.patch].reshape(b, c, n, self.patch).permute(0, 2, 1, 3).reshape(b, n, -1))
        tok = self.tpg(tok, self.prototypes.expand(b, -1, -1))
        with torch.autocast(x.device.type, enabled=False):
            s = x.float().mean(1)
            p = torch.fft.rfft(s - s.mean(-1, keepdim=True)).abs()
            dom = p.argmax(-1).float() * fps.float() / t
            stats = torch.stack([s.mean(-1), s.std(-1), dom], -1)
        extra = [self.prior(stats.to(tok.dtype))[:, None]]
        if prompt_embedding is not None:
            extra.append(prompt_embedding.to(tok.dtype))
        h = self.lm(torch.cat(extra + [tok], 1))[:, -n:]
        y = self.out(h).reshape(b, n, c, self.patch).permute(0, 2, 1, 3).reshape(b, c, n * self.patch)
        return x + F.pad(y, (0, t - n * self.patch))
