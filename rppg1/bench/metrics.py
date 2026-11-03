"""Video-level HR evaluation, reproducing rPPG-Toolbox evaluation/post_process.py and metrics.py:
  DiffNormalized signals are integrated (cumsum), detrended (smoothness priors, lambda 100), band-passed
  (1st-order Butterworth, 0.75-2.5 Hz), and HR = periodogram peak in 0.75-2.5 Hz over the WHOLE video
  (EVALUATION_METHOD FFT, USE_SMALLER_WINDOW False). Metrics: MAE, RMSE, MAPE, Pearson r and SNR, each with the
  toolbox's standard error.
"""
import numpy as np
from scipy import signal as sps
from scipy import sparse
from scipy.sparse.linalg import spsolve

LOW, HIGH = 0.75, 2.5
# Datasets whose videos carry a codec artefact inside the heart-rate band: a narrow peak at fps / period and its
# harmonics (MPSC-rPPG phone videos: 29.97 / 15 = 1.998 Hz, 119.9 bpm). Those bins are skipped when picking the HR
# peak, for every method alike. Narrow (+-0.03 Hz = +-1.8 bpm), so a true HR near 120 bpm is lost only within that.
CODEC_PERIOD = {"MPSC-rPPG": 15}
NOTCH_HZ = 0.03


def codec_notch(meta):
    k = CODEC_PERIOD.get(meta.get("dataset"))
    return tuple(meta["fps"] / k * i for i in range(1, 4)) if k else ()


def detrend(x, lam=100):
    """Tarvainen et al. 2002 smoothness-priors detrending (sparse solve instead of the toolbox's dense inverse)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    d = sparse.diags([np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)], [0, 1, 2], shape=(n - 2, n))
    return x - spsolve((sparse.identity(n) + lam ** 2 * (d.T @ d)).tocsc(), x)


def post_process(x, fs, diff_flag):
    x = detrend(np.cumsum(x) if diff_flag else x, 100)
    b, a = sps.butter(1, [LOW / fs * 2, HIGH / fs * 2], btype="bandpass")
    return sps.filtfilt(b, a, x.astype(np.float64))


def fft_hr(x, fs, notch=()):
    n = 1 << (len(x) - 1).bit_length()
    f, p = sps.periodogram(x, fs=fs, nfft=n, detrend=False)
    m = (f >= LOW) & (f <= HIGH)
    for f0 in notch:
        m &= np.abs(f - f0) > NOTCH_HZ
    return float(f[m][np.argmax(p[m])] * 60)


def snr_db(x, hr_label, fs, dev_bpm=6):
    n = 1 << (len(x) - 1).bit_length()
    f, p = sps.periodogram(x, fs=fs, nfft=n, detrend=False)
    f1, f2, dev = hr_label / 60, 2 * hr_label / 60, dev_bpm / 60
    band = (f >= LOW) & (f <= HIGH)
    sig = band & (((f >= f1 - dev) & (f <= f1 + dev)) | ((f >= f2 - dev) & (f <= f2 + dev)))
    s, r = p[sig].sum(), p[band & ~sig].sum()
    return float(10 * np.log10(s / r)) if s > 0 and r > 0 else 0.0


def video_hr(pred, label, fs, diff_flag, notch=()):
    """-> (predicted HR, label HR, SNR dB) for one whole video; notch = codec artefact frequencies to skip."""
    p, l = post_process(pred, fs, diff_flag), post_process(label, fs, diff_flag)
    hr_l = fft_hr(l, fs)
    return fft_hr(p, fs, notch), hr_l, snr_db(p, hr_l, fs)


def summary(hr_pred, hr_label, snrs):
    p, l, s = np.asarray(hr_pred), np.asarray(hr_label), np.asarray(snrs)
    n = len(p)
    err = p - l
    mae, rmse = np.mean(np.abs(err)), np.sqrt(np.mean(err ** 2))
    mape = np.mean(np.abs(err / l)) * 100
    r = float(np.corrcoef(p, l)[0, 1]) if n > 2 and p.std() > 0 and l.std() > 0 else float("nan")
    return {"n_videos": n,
            "MAE": float(mae), "MAE_se": float(np.std(np.abs(err)) / np.sqrt(n)),
            "RMSE": float(rmse), "RMSE_se": float(np.std(err ** 2) / np.sqrt(n)),
            "MAPE": float(mape), "MAPE_se": float(np.std(np.abs(err / l)) / np.sqrt(n) * 100),
            "Pearson": r, "Pearson_se": float(np.sqrt((1 - r ** 2) / (n - 2))) if n > 2 and r == r else float("nan"),
            "SNR": float(np.mean(s)), "SNR_se": float(np.std(s) / np.sqrt(n)),
            "within_5bpm": float(np.mean(np.abs(err) <= 5))}
