"""Signal helpers shared by the measurement agents (adapted from rppg1/webapp/vitals.py).

Every function returns None rather than a number when the input is too short or degenerate to support it.
"""
import numpy as np
from scipy import signal as sps

HR_BAND_HZ = (0.7, 3.0)      # 42-180 bpm
RR_BAND_HZ = (0.1, 0.7)      # 6-42 breaths/min (brief P1: thermal nostril band)


def bandpass(x, fs, low_hz, high_hz, order=3):
    x = np.asarray(x, dtype=np.float64)
    nyq = fs / 2.0
    low, high = low_hz / nyq, min(high_hz / nyq, 0.99)
    if not (0 < low < high < 1) or x.size <= 6 * (order + 1):
        return None
    b, a = sps.butter(order, [low, high], btype="band")
    return sps.filtfilt(b, a, x)


def _spectrum(x, fs):
    x = np.asarray(x, dtype=np.float64)
    if x.size < 8:
        return None, None
    x = sps.detrend(x)
    if x.std() < 1e-12:
        return None, None
    x = x / x.std()
    nfft = max(int(2 ** np.ceil(np.log2(x.size))) * 4, 2048)
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fs)
    return freqs, np.abs(np.fft.rfft(x * np.hanning(x.size), n=nfft)) ** 2


def _band_mask(freqs, band, exclude=()):
    m = (freqs >= band[0]) & (freqs <= band[1])
    for lo, hi in exclude:
        m &= ~((freqs >= lo) & (freqs <= hi))
    return m


def peak_hz(x, fs, band, exclude=()):
    """Dominant frequency (Hz) inside `band`, ignoring the `exclude` (lo, hi) bands."""
    freqs, power = _spectrum(x, fs)
    if freqs is None:
        return None
    m = _band_mask(freqs, band, exclude)
    return float(freqs[m][np.argmax(power[m])]) if m.any() else None


def snr_db(x, fs, band=HR_BAND_HZ, half_width=0.2, harmonic=True, exclude=()):
    """Power within +-half_width Hz of the dominant frequency (and its first harmonic) against the rest of the band;
    `exclude` bands count as neither."""
    freqs, power = _spectrum(x, fs)
    if freqs is None:
        return None
    m = _band_mask(freqs, band, exclude)
    if not m.any():
        return None
    f0 = freqs[m][np.argmax(power[m])]
    sig = np.zeros_like(m)
    for c in ((f0, 2 * f0) if harmonic else (f0,)):
        sig |= (freqs >= c - half_width) & (freqs <= c + half_width)
    sig &= m
    s, n = power[sig].sum(), power[m & ~sig].sum()
    return float(10 * np.log10(s / n)) if s > 0 and n > 0 else None


def halves(n, fs, min_seconds):
    """Index ranges of two equal halves when each lasts >= min_seconds, else one range over everything."""
    if n / fs >= 2 * min_seconds:
        return [(0, n // 2), (n // 2, n)]
    return [(0, n)]


def ramp(x, lo, hi):
    """Linear 0..1 between lo and hi (clipped); None -> 0."""
    return 0.0 if x is None else float(np.clip((x - lo) / (hi - lo), 0, 1))
