"""
Physiological measures derived from a predicted rPPG waveform.

Beyond heart rate, the rPPG waveform supports the measures the PhysFormer
paper itself evaluates (Table 2: HR, respiration frequency, LF, HF, LF/HF)
plus standard time-domain HRV indices and a signal-quality estimate.

Every function returns None (rather than a garbage number) when the input
window is too short or too degenerate to support the measure.
"""
import numpy as np
from scipy import signal as sps

HR_BAND_HZ = (0.7, 3.0)      # 42-180 bpm
RR_BAND_HZ = (0.1, 0.5)      # 6-30 breaths/min
LF_BAND_HZ = (0.04, 0.15)
HF_BAND_HZ = (0.15, 0.40)


def _detrend_normalize(x):
    x = np.asarray(x, dtype=np.float64)
    if x.size < 4:
        return None
    x = sps.detrend(x)
    std = x.std()
    if std < 1e-8:
        return None
    return x / std


def bandpass(x, fps, low_hz, high_hz, order=3):
    """Zero-phase Butterworth bandpass. Returns None if the band is invalid
    for this sample rate or the signal is too short to filter."""
    x = np.asarray(x, dtype=np.float64)
    nyq = fps / 2.0
    low, high = low_hz / nyq, min(high_hz / nyq, 0.99)
    if not (0 < low < high < 1):
        return None
    padlen = 3 * order + 1
    if x.size <= padlen * 2:
        return None
    b, a = sps.butter(order, [low, high], btype="band")
    return sps.filtfilt(b, a, x)


def _band_peak_hz(x, fps, band, nfft=None):
    """Dominant frequency (Hz) within `band` via periodogram peak."""
    x = _detrend_normalize(x)
    if x is None:
        return None
    nfft = nfft or max(int(2 ** np.ceil(np.log2(max(x.size, 2)))) * 4, 2048)
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fps)
    power = np.abs(np.fft.rfft(x * np.hanning(x.size), n=nfft)) ** 2
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if not mask.any():
        return None
    return float(freqs[mask][np.argmax(power[mask])])


def estimate_hr(waveform, fps):
    """Heart rate in bpm from the rPPG spectral peak."""
    f = _band_peak_hz(waveform, fps, HR_BAND_HZ)
    return None if f is None else f * 60.0


def estimate_rr(waveform, fps, min_seconds=20.0):
    x = np.asarray(waveform, dtype=np.float64)
    if x.size < min_seconds * fps:
        return None
    f = _band_peak_hz(x, fps, RR_BAND_HZ)
    return None if f is None else f * 60.0

def detect_beats(waveform, fps, max_bpm=180):
    filt = bandpass(waveform, fps, *HR_BAND_HZ)
    if filt is None:
        return None
    std = filt.std()
    if std < 1e-8:
        return None
    min_distance = max(int(fps * 60.0 / max_bpm), 1)
    peaks, _ = sps.find_peaks(filt, distance=min_distance, prominence=0.4 * std)
    return peaks

def compute_ibi(waveform, fps, max_bpm=180):
    """Inter-beat intervals in milliseconds."""
    peaks = detect_beats(waveform, fps, max_bpm=max_bpm)
    if peaks is None or peaks.size < 3:
        return None
    ibi = np.diff(peaks) / fps * 1000.0
    # drop physiologically impossible intervals (<333ms = >180bpm, >2000ms = <30bpm)
    ibi = ibi[(ibi >= 333.0) & (ibi <= 2000.0)]
    return ibi if ibi.size >= 2 else None


def hrv_time_domain(ibi):
    """SDNN, RMSSD, pNN50 (ms, ms, %) from an inter-beat-interval series."""
    if ibi is None or len(ibi) < 3:
        return None
    ibi = np.asarray(ibi, dtype=np.float64)
    diffs = np.diff(ibi)
    return {
        "mean_ibi_ms": float(ibi.mean()),
        "sdnn_ms": float(ibi.std(ddof=1)),
        "rmssd_ms": float(np.sqrt(np.mean(diffs ** 2))),
        "pnn50_pct": float(np.mean(np.abs(diffs) > 50.0) * 100.0),
    }


def hrv_frequency_domain(ibi, resample_hz=4.0, min_beats=20):
    """LF / HF power in normalized units plus the LF/HF ratio.

    The tachogram is resampled onto a uniform grid before Welch's method,
    as LF/HF are defined on evenly sampled interval series.
    """
    if ibi is None or len(ibi) < min_beats:
        return None
    ibi = np.asarray(ibi, dtype=np.float64)
    times = np.cumsum(ibi) / 1000.0
    duration = times[-1] - times[0]
    if duration < 20.0:
        return None

    uniform_t = np.arange(times[0], times[-1], 1.0 / resample_hz)
    if uniform_t.size < 16:
        return None
    tacho = np.interp(uniform_t, times, ibi)
    tacho = sps.detrend(tacho)

    nperseg = min(256, tacho.size)
    freqs, psd = sps.welch(tacho, fs=resample_hz, nperseg=nperseg)

    def band_power(band):
        mask = (freqs >= band[0]) & (freqs < band[1])
        return float(np.trapezoid(psd[mask], freqs[mask])) if mask.any() else 0.0

    lf, hf = band_power(LF_BAND_HZ), band_power(HF_BAND_HZ)
    total = lf + hf
    if total <= 0:
        return None
    return {
        "lf_nu": lf / total,
        "hf_nu": hf / total,
        "lf_hf_ratio": (lf / hf) if hf > 0 else None,
    }


def signal_quality_db(waveform, fps):
    """SNR (dB) of the rPPG waveform: power within +/-0.2 Hz of the dominant
    pulse frequency and its first harmonic, against the rest of the HR band.

    This is the honest confidence signal -- a low value means the derived
    HR/HRV numbers should not be trusted.
    """
    x = _detrend_normalize(waveform)
    if x is None or x.size < fps * 2:
        return None
    nfft = max(int(2 ** np.ceil(np.log2(x.size))) * 4, 2048)
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fps)
    power = np.abs(np.fft.rfft(x * np.hanning(x.size), n=nfft)) ** 2

    band = (freqs >= HR_BAND_HZ[0]) & (freqs <= HR_BAND_HZ[1])
    if not band.any():
        return None
    f0 = freqs[band][np.argmax(power[band])]

    signal_mask = np.zeros_like(freqs, dtype=bool)
    for center in (f0, 2 * f0):
        signal_mask |= (freqs >= center - 0.2) & (freqs <= center + 0.2)
    signal_mask &= band
    noise_mask = band & ~signal_mask

    sig_p, noise_p = power[signal_mask].sum(), power[noise_mask].sum()
    if noise_p <= 0 or sig_p <= 0:
        return None
    return float(10.0 * np.log10(sig_p / noise_p))


def compute_all(waveform, fps):
    """Every derived measure for the current waveform window."""
    out = {
        "hr_bpm": estimate_hr(waveform, fps),
        "rr_brpm": estimate_rr(waveform, fps),
        "snr_db": signal_quality_db(waveform, fps),
        "sdnn_ms": None, "rmssd_ms": None, "pnn50_pct": None, "mean_ibi_ms": None,
        "lf_nu": None, "hf_nu": None, "lf_hf_ratio": None,
        "n_beats": 0,
    }
    ibi = compute_ibi(waveform, fps)
    if ibi is not None:
        out["n_beats"] = int(len(ibi) + 1)
        time_dom = hrv_time_domain(ibi)
        if time_dom:
            out.update(time_dom)
        freq_dom = hrv_frequency_domain(ibi)
        if freq_dom:
            out.update(freq_dom)
    return out
