"""Shared spectral helpers. Clips come at different frame rates (MCD-rPPG ~24 fps, UBFC 30 fps), so every bin's
physical frequency is computed per clip from its own fps."""
import torch


def nfft_for(t, minimum=256):
    n = minimum
    while n < t:
        n *= 2
    return n


def bin_freqs(fps, n):
    """fps (B,) -> (B, n//2+1) frequency of each rfft bin in Hz."""
    return torch.arange(n // 2 + 1, device=fps.device, dtype=torch.float32)[None, :] * fps.float()[:, None] / n


def band_mask(freqs, band):
    return ((freqs >= band[0]) & (freqs <= band[1])).float()


def spectrum(x, fps, n=None):
    """x (B,T) -> power (B,F), freqs (B,F); mean removed, zero-padded FFT."""
    n = n or nfft_for(x.shape[-1])
    p = torch.fft.rfft(x - x.mean(-1, keepdim=True), n=n).abs() ** 2
    return p, bin_freqs(fps, n)


def interp_matrix(src, dst):
    """Linear-interpolation weights from values at points src (B,F) to points dst (B,G) or (G,) -> (B,G,F).
    src ascending; dst outside src is clamped to the end points."""
    if dst.dim() == 1:
        dst = dst[None, :].expand(src.shape[0], -1)
    dst = dst.contiguous()
    i = torch.searchsorted(src.contiguous(), dst).clamp(1, src.shape[1] - 1)
    lo, hi = src.gather(1, i - 1), src.gather(1, i)
    w = ((dst - lo) / (hi - lo).clamp_min(1e-8)).clamp(0, 1)
    m = torch.zeros(src.shape[0], dst.shape[1], src.shape[1], device=src.device)
    m.scatter_(2, (i - 1)[..., None], (1 - w)[..., None])
    m.scatter_add_(2, i[..., None], w[..., None])
    return m
