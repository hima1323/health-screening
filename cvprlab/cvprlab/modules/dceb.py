"""(4) Dual-stream confidence-gated exchange (PhysNeXt).

1. Spatial alignment: each branch is gathered onto the same S learned slots (one set of logits per branch,
   softmaxed over positions to gather and over slots to scatter), so a cheek in the video grid and a cheek column of
   the STMap can land in the same slot.
2. Frequency matching: each branch's pooled temporal signature gives a confidence (fraction of spectral energy in
   the cardiac band) and the two band-limited spectra give an agreement score.
3. Confidence gating: slot-wise cross-attention (per time step) computes what each branch would borrow; the
   residual is scaled by a gate driven by the OTHER branch's confidence and the agreement.
Also emits a per-time-step reliability in (0, 1) for the decoder.
"""
import torch
import torch.nn as nn

from cvprlab.modules.attention import CrossAttention, fold_time, unfold_time
from cvprlab.modules.spectral import band_mask, spectrum


class SlotMap(nn.Module):
    def __init__(self, slots, positions):
        super().__init__()
        self.logits = nn.Parameter(torch.randn(slots, positions) * 0.02)

    def gather(self, x):           # (B,C,T,P) -> (B,C,T,S)
        return torch.einsum("bctp,sp->bcts", x, self.logits.softmax(dim=1))

    def scatter(self, s):          # (B,C,T,S) -> (B,C,T,P)
        return torch.einsum("bcts,sp->bctp", s, self.logits.softmax(dim=0))


class DCEB(nn.Module):
    def __init__(self, cfg, video_positions, stmap_positions):
        super().__init__()
        d, s = cfg.dim, cfg.dceb_slots
        self.band = cfg.band_hz
        self.map_v, self.map_s = SlotMap(s, video_positions), SlotMap(s, stmap_positions)
        self.sig_v, self.sig_s = nn.Linear(d, 1), nn.Linear(d, 1)
        self.borrow_v, self.borrow_s = CrossAttention(d, cfg.heads), CrossAttention(d, cfg.heads)
        self.gate = nn.Parameter(torch.tensor([4.0, 4.0, -4.0]))   # a * conf_other + b * match + c
        self.rel = nn.Sequential(nn.Conv1d(2, 16, 5, padding=2), nn.GELU(), nn.Conv1d(16, 1, 5, padding=2))

    def signature(self, slots, proj):              # (B,C,T,S) -> (B,T)
        return proj(slots.permute(0, 2, 3, 1)).squeeze(-1).mean(-1)

    def forward(self, fv, fs, fps):
        b = fv.shape[0]
        sv, ss = self.map_v.gather(fv), self.map_s.gather(fs)
        gv, gs = self.signature(sv, self.sig_v), self.signature(ss, self.sig_s)
        with torch.autocast(fv.device.type, enabled=False):
            pv, freqs = spectrum(gv.float(), fps)
            ps, _ = spectrum(gs.float(), fps)
            m = band_mask(freqs, self.band)
            conf_v = (pv * m).sum(-1) / pv.sum(-1).clamp_min(1e-8)
            conf_s = (ps * m).sum(-1) / ps.sum(-1).clamp_min(1e-8)
            av, as_ = (pv * m + 1e-12).sqrt() * m, (ps * m + 1e-12).sqrt() * m     # eps: sqrt'(0) is infinite
            match = (av * as_).sum(-1) / (av.norm(dim=-1) * as_.norm(dim=-1)).clamp_min(1e-8)
        a, bb, c = self.gate
        gate_v = torch.sigmoid(a * conf_s + bb * match + c).to(fv.dtype)[:, None, None, None]
        gate_s = torch.sigmoid(a * conf_v + bb * match + c).to(fv.dtype)[:, None, None, None]
        tv, ts = fold_time(sv), fold_time(ss)
        dv = unfold_time(self.borrow_v(tv, ts) - tv, b)
        ds = unfold_time(self.borrow_s(ts, tv) - ts, b)
        fv = fv + self.map_v.scatter(gate_v * dv)
        fs = fs + self.map_s.scatter(gate_s * ds)
        r = torch.sigmoid(self.rel(torch.stack([gv, gs], 1))).squeeze(1)
        return fv, fs, torch.stack([conf_v, conf_s], 1), r
