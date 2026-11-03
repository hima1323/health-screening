"""(10) Structured attention fusion decoder (PhysNeXt), and the plain conv head used without it.

A state token (from both branches' confidences and the pooled features) plus learned query tokens read the temporal
features through attention biased by log(reliability): an untrusted instant is attenuated, not hard-masked (one
blink must not delete a whole time step). The time axis then reads the tokens back, expanding a handful of global
tokens into a full-length waveform.
"""
import torch
import torch.nn as nn

from cvprlab.modules.attention import CrossAttention


class ConvHead(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.net = nn.Sequential(nn.Conv1d(dim, dim // 2, 3, padding=1), nn.BatchNorm1d(dim // 2), nn.ELU(),
                                 nn.Conv1d(dim // 2, 1, 3, padding=1))

    def forward(self, x, *_):
        return self.net(x).squeeze(1)


class SAFD(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        d = cfg.dim
        self.state = nn.Linear(d + 2, d)
        self.queries = nn.Parameter(torch.randn(1, cfg.decoder_queries, d) * 0.02)
        self.read = CrossAttention(d, cfg.heads)
        self.write = CrossAttention(d, cfg.heads)
        self.head = ConvHead(d)
        self.heads = cfg.heads

    def forward(self, x, reliability=None, conf=None):
        """x (B,C,T); reliability (B,T) in (0,1) or None; conf (B,2) or None -> (B,T)"""
        b = x.shape[0]
        t = x.transpose(1, 2)
        conf = conf if conf is not None else x.new_ones(b, 2)
        tokens = torch.cat([self.state(torch.cat([t.mean(1), conf.to(t.dtype)], -1))[:, None],
                            self.queries.expand(b, -1, -1)], 1)
        bias = None if reliability is None else reliability.clamp_min(1e-4).log().to(t.dtype)[:, None, None, :]
        tokens = self.read(tokens, t, bias)
        t = self.write(t, tokens)
        return self.head(t.transpose(1, 2))
