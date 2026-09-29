import torch


def signal_to_hr(signal, fps=30, low_bpm=42, high_bpm=180, n_fft=None):
    """Estimate HR (bpm) from a 1D rPPG signal via its dominant PSD peak
    within the plausible band, as used at test time (Sec. 4.2).
    """
    t = signal.shape[-1]
    n_fft = n_fft or max(t, 2048)
    signal = signal - signal.mean(dim=-1, keepdim=True)
    spec = torch.fft.rfft(signal, n=n_fft, dim=-1)
    power = spec.real ** 2 + spec.imag ** 2
    freqs = torch.fft.rfftfreq(n_fft, d=1.0 / fps).to(signal.device)
    bpm = freqs * 60.0
    mask = (bpm >= low_bpm) & (bpm <= high_bpm)
    power = power[..., mask]
    bpm = bpm[mask]
    idx = power.argmax(dim=-1)
    return bpm[idx]
