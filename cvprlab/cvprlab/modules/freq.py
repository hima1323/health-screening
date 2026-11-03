"""(6) Physiological frequency denoiser and (7) cross-domain fusion (FreqPhys).

PBF: hard gate keeping 0.66-3.0 Hz (40-180 bpm).
PSM: learnable complex weights on the surviving spectrum - a pointwise product in frequency is a global circular
     convolution in time, a clip-wide receptive field for a few thousand parameters. The weights live on a fixed
     grid of `psm_bins` physical frequencies and are interpolated onto each clip's bins, so one set of weights
     serves 24 fps and 30 fps clips alike.
ASS: a learned per-channel energy threshold squelches bins still too weak to trust (sigmoid, so differentiable).
The FFT is zero-padded to >= 256 points (0.12 Hz bins at 30 fps instead of 0.19 Hz), which also makes PSM's implied
convolution effectively linear. Runs in float32 (fp16 FFTs need power-of-two sizes and lose precision).
"""
import torch
import torch.nn as nn

from cvprlab.modules.attention import CrossAttention
from cvprlab.modules.spectral import band_mask, bin_freqs, interp_matrix, nfft_for


class FreqDenoiser(nn.Module):
    def __init__(self, cfg, use_psm=True, use_ass=True):
        super().__init__()
        self.band, self.nmin, self.temp = cfg.band_hz, cfg.nfft_min, cfg.ass_temperature
        self.use_psm, self.use_ass = use_psm, use_ass
        self.register_buffer("grid", torch.linspace(cfg.band_hz[0], cfg.band_hz[1], cfg.psm_bins), persistent=False)
        self.w_re = nn.Parameter(torch.ones(cfg.dim, cfg.psm_bins))
        self.w_im = nn.Parameter(torch.zeros(cfg.dim, cfg.psm_bins))
        self.thr = nn.Parameter(torch.full((cfg.dim, 1), -3.0))

    def forward(self, x, fps):
        """x (B,C,T) -> band-limited time features (B,C,T), spectrum tokens (B,psm_bins,2C)."""
        t = x.shape[-1]
        with torch.autocast(x.device.type, enabled=False):
            x = x.float()
            n = nfft_for(t, self.nmin)
            X = torch.fft.rfft(x - x.mean(-1, keepdim=True), n=n)                 # (B,C,F)
            f = bin_freqs(fps, n)                                                 # (B,F)
            m = band_mask(f, self.band)[:, None, :]
            X = X * m                                                             # PBF
            if self.use_psm:                                                      # PSM, grid -> each clip's bins
                to_bins = interp_matrix(self.grid[None, :].expand(f.shape[0], -1), f.clamp(*self.band))  # (B,F,G)
                w = torch.complex(torch.einsum("cg,bfg->bcf", self.w_re, to_bins),
                                  torch.einsum("cg,bfg->bcf", self.w_im, to_bins))
                X = X * w
            if self.use_ass:                                                      # ASS
                e = X.abs() ** 2
                e = e / ((e * m).sum(-1, keepdim=True) / m.sum(-1, keepdim=True).clamp_min(1)).clamp_min(1e-12)
                X = X * torch.sigmoid((torch.log(e + 1e-12) - self.thr) / self.temp)
            y = torch.fft.irfft(X, n=n)[..., :t]
            to_grid = interp_matrix(f, self.grid)                                 # (B,G,F)
            tok = torch.complex(torch.einsum("bcf,bgf->bgc", X.real, to_grid),
                                torch.einsum("bcf,bgf->bgc", X.imag, to_grid))
        return y, torch.cat([tok.real, tok.imag], -1)


class CrossDomain(nn.Module):
    """Alternating cross-attention between T time tokens and the in-band frequency tokens."""

    def __init__(self, cfg):
        super().__init__()
        d = cfg.dim
        self.spec_in = nn.Linear(2 * d, d)
        self.pos = nn.Parameter(torch.zeros(1, cfg.psm_bins, d))
        self.t_from_f = nn.ModuleList([CrossAttention(d, cfg.heads) for _ in range(cfg.cross_domain_layers)])
        self.f_from_t = nn.ModuleList([CrossAttention(d, cfg.heads) for _ in range(cfg.cross_domain_layers)])

    def forward(self, x, spec):
        """x (B,C,T), spec (B,G,2C) -> (B,C,T)"""
        t, f = x.transpose(1, 2), self.spec_in(spec.to(x.dtype)) + self.pos
        for tf, ft in zip(self.t_from_f, self.f_from_t):
            t, f = tf(t, f), ft(f, t)
        return t.transpose(1, 2)
