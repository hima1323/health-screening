"""Window features per subject -> data/features/<subject>.parquet.

Each kept segment is processed once (NeuroKit2), then cut into 30 s windows with 50% overlap.
Only raw values are stored; per-subject z-scores are added at load time by `zscore()` (see there).

    python src/features.py --subject 0                 # one subject (downloads if missing)
    python src/features.py --all --delete-raw          # download -> extract -> delete raw, one subject at a time
"""
import argparse
import time
import warnings

import neurokit2 as nk
import numpy as np
import pandas as pd
from scipy.signal import resample_poly

import quality as Q
from load_adabase import KEEP, ROOT, SUBJECTS, Subject, download, subject_id

warnings.filterwarnings("ignore")
FEAT = ROOT / "data" / "features"
WIN, STEP, FS = 30.0, 15.0, 1000  # window s, step s, bio-signal rate on the ADABase grid
AUS = ["AU01", "AU02", "AU04", "AU05", "AU06", "AU07", "AU09", "AU10", "AU11", "AU12", "AU14", "AU15",
       "AU17", "AU20", "AU23", "AU24", "AU25", "AU26", "AU28", "AU43"]
# modality of every feature (prefix before the first '_'); used for ablations and modality dropout
MODALITIES = {"ecg": "contact", "ppg": "contact", "eda": "contact", "rsp": "contact", "emg": "contact",
              "skt": "contact", "eye": "contactless", "au": "contactless"}


def down(x, factor):
    return resample_poly(x, 1, factor)


def process_segment(df):
    """Whole-segment processing. Returns event times (s) and slow signals on their own time base."""
    out = {}
    ecg = df.RAW_ECG_I.to_numpy()
    try:
        out["r"] = nk.ecg_peaks(nk.ecg_clean(ecg, sampling_rate=FS), sampling_rate=FS)[1]["ECG_R_Peaks"] / FS
    except Exception:
        out["r"] = np.array([])

    ppg = nk.ppg_clean(df.RAW_PPG.to_numpy(), sampling_rate=FS)
    try:
        pk = nk.ppg_findpeaks(ppg, sampling_rate=FS)["PPG_Peaks"]
    except Exception:
        pk = np.array([], int)
    # foot = minimum in the 400 ms before each systolic peak
    ft = np.array([max(p - 400, 0) + np.argmin(ppg[max(p - 400, 0):p + 1]) for p in pk], int)
    out["ppg_peak"], out["ppg_foot"], out["ppg_amp"] = pk / FS, ft / FS, ppg[pk] - ppg[ft]

    eda = down(df.RAW_EDA.to_numpy(), 20)  # 50 Hz
    try:
        sig, info = nk.eda_process(eda, sampling_rate=50)
        out["eda_tonic"] = sig.EDA_Tonic.to_numpy()
        ok = np.isfinite(info["SCR_Peaks"]) & np.isfinite(info["SCR_Amplitude"])
        out["scr_t"], out["scr_amp"] = info["SCR_Peaks"][ok] / 50, info["SCR_Amplitude"][ok]
    except Exception:
        out["eda_tonic"], out["scr_t"], out["scr_amp"] = np.full(len(eda), np.nan), np.array([]), np.array([])
    out["eda_raw"] = eda

    rsp = down(df.RAW_RSP.to_numpy(), 20)  # 50 Hz
    try:
        sig, info = nk.rsp_process(rsp, sampling_rate=50)
        out["rsp_rate"], out["rsp_amp"] = sig.RSP_Rate.to_numpy(), sig.RSP_Amplitude.to_numpy()
        out["breath_t"] = info["RSP_Peaks"] / 50
    except Exception:
        out["rsp_rate"] = out["rsp_amp"] = np.full(len(rsp), np.nan)
        out["breath_t"] = np.array([])

    out["emg"] = nk.emg_clean(df.RAW_EMG.to_numpy(), sampling_rate=FS)
    out["skt"] = down(df.RAW_SKT.to_numpy(), 100)  # 10 Hz
    return out


def eye_features(e):
    """e: eye-tracker rows of one window (250 Hz). Pupil, blinks, fixations, quality."""
    n = len(e)
    if n < 250:
        return {"q_eye": 0.0}
    valid = (e.EYE_LEFT_PUPIL_VALIDITY.to_numpy() > 0) | (e.EYE_RIGHT_PUPIL_VALIDITY.to_numpy() > 0)
    t = e.t.to_numpy()
    p = e.EYE_MEAN_PUPIL_DIAMETER.to_numpy()
    m = valid & np.isfinite(p)
    f = {"q_eye": float(m.mean())}
    if m.sum() > 250:
        f["eye_pupil_mean"] = float(np.mean(p[m]))
        f["eye_pupil_slope"] = float(np.polyfit(t[m], p[m], 1)[0])
    # blinks: runs of invalid pupil lasting 75-500 ms
    edges = np.diff(np.r_[0, (~valid).astype(int), 0])
    dur = (np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)) / 250
    f["eye_blink_rate"] = float(((dur >= 0.075) & (dur <= 0.5)).sum() / (n / 250) * 60)
    # fixations: I-VT, 30 deg/s, on the left-eye gaze direction (gaze point - gaze origin, user coords, mm)
    g = e[[f"EYE_LEFT_GAZE_POINT_IN_USER_COORDINATE_SYSTEM_{a}" for a in "XYZ"]].to_numpy() \
        - e[[f"EYE_LEFT_GAZE_ORIGIN_IN_USER_COORDINATE_SYSTEM_{a}" for a in "XYZ"]].to_numpy()
    g = pd.DataFrame(g).rolling(7, center=True).mean().to_numpy()  # 28 ms smoothing; raw noise ~0.3 deg/sample
    g /= np.linalg.norm(g, axis=1, keepdims=True)
    ang = np.degrees(np.arccos(np.clip((g[1:] * g[:-1]).sum(1), -1, 1)))
    fix = np.r_[False, ang * 250 < 30]  # NaN gaze -> False, so gaps end fixations
    edges = np.diff(np.r_[0, fix.astype(int), 0])
    fd = (np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)) / 250
    fd = fd[fd >= 0.06]
    if len(fd):
        f["eye_fix_dur"] = float(fd.mean())
    return f


def window_features(seg, a, b, face, eye):
    """Features of window [a, b) seconds. `seg` = process_segment output."""
    f = {}
    within = lambda ts: ts[(ts >= a) & (ts < b)]
    sl = lambda x, fs: x[int(a * fs):int(b * fs)]

    r = within(seg["r"])
    f["q_ecg"] = Q.beats(r)
    rr = np.diff(r) * 1000
    rr = rr[(rr > 300) & (rr < 2000)]
    if len(rr) > 5:
        f["ecg_hr"] = 60000 / rr.mean()
        f["ecg_rmssd"] = np.sqrt(np.mean(np.diff(rr) ** 2))
        f["ecg_sdnn"] = rr.std(ddof=1)
        f["ecg_pnn50"] = (np.abs(np.diff(rr)) > 50).mean() * 100
    # LF/HF skipped: a 30 s window cannot resolve LF (0.04-0.15 Hz)

    pk = seg["ppg_peak"]
    m = (pk >= a) & (pk < b)
    f["q_ppg"] = Q.beats(pk[m])
    if m.sum() > 5:
        f["ppg_rate"] = 60 / np.diff(pk[m]).mean()
        f["ppg_amp"] = float(np.median(seg["ppg_amp"][m]))
        # pulse transit time: R peak -> next PPG foot within 100-600 ms
        ft = seg["ppg_foot"][m]
        idx = np.searchsorted(ft, r)
        ptt = np.array([ft[i] - rt for i, rt in zip(idx, r) if i < len(ft)])
        ptt = ptt[(ptt > 0.1) & (ptt < 0.6)]
        if len(ptt) > 5:
            f["ppg_ptt"] = float(np.median(ptt) * 1000)

    tonic = sl(seg["eda_tonic"], 50)
    f["q_eda"] = Q.smooth(sl(seg["eda_raw"], 50))
    if np.isfinite(tonic).any():
        f["eda_tonic"] = float(np.nanmean(tonic))
    st = seg["scr_t"]
    sm = (st >= a) & (st < b)
    f["eda_scr_count"] = float(sm.sum())
    f["eda_scr_amp"] = float(seg["scr_amp"][sm].mean()) if sm.any() else 0.0

    br = within(seg["breath_t"])
    f["q_rsp"] = Q.breaths(br)
    rate = sl(seg["rsp_rate"], 50)
    if np.isfinite(rate).any():
        f["rsp_rate"] = float(np.nanmean(rate))
        f["rsp_depth"] = float(np.nanmean(sl(seg["rsp_amp"], 50)))
    if len(br) > 3:
        f["rsp_var"] = float(np.std(np.diff(br)) / np.mean(np.diff(br)))  # CV of breath intervals

    emg = sl(seg["emg"], FS)
    f["q_emg"] = Q.coverage(emg, int((b - a) * FS))
    f["emg_rms"] = float(np.sqrt(np.nanmean(emg ** 2)))

    skt = sl(seg["skt"], 10)
    f["q_skt"] = Q.smooth(skt)
    f["skt_mean"] = float(np.nanmean(skt))
    f["skt_slope"] = float(np.polyfit(np.arange(len(skt)) / 10, skt, 1)[0]) if len(skt) > 10 else np.nan

    f.update(eye_features(eye[(eye.t >= a) & (eye.t < b)]))

    fw = face[(face.t >= a) & (face.t < b)]
    f["q_au"] = float(Q.coverage(fw.FACE_SCORE.to_numpy(), int((b - a) * 25)) * fw.FACE_SCORE.mean()) if len(fw) else 0.0
    if len(fw) > 25 * 5:
        for au in AUS:
            f[f"au_{au[2:]}"] = float((fw[f"FACE_{au}"] > 0.5).mean())  # activation rate
    return f


def extract(sid):
    s = Subject(sid)
    tlx = s.tlx()
    rows = []
    for g in s.segments().itertuples():
        if (g.study, g.phase, g.level) not in KEEP:
            continue
        df = s.read(g.start, g.stop)
        dur = df.t.iloc[-1]
        seg = process_segment(df)
        face = df.loc[df.FACE_SCORE.notna(), ["t", "FACE_SCORE"] + [f"FACE_{a}" for a in AUS]]
        eye = df.loc[df.EYE_LEFT_PUPIL_VALIDITY.notna(), ["t"] + [c for c in df.columns if c.startswith("EYE_")]]
        del df
        for a in np.arange(0, dur - WIN + 1e-6, STEP):
            f = window_features(seg, a, a + WIN, face, eye)
            nb = (g.level - 1) % 3 + 1 if g.study == "n-back" and g.phase == "test" else 0
            rows.append({"subject": sid, "study": g.study, "phase": g.phase, "level": g.level, "win_start": a,
                         "nback_n": nb, "dual": int(g.study == "n-back" and g.phase == "test" and g.level > 3),
                         "tlx": tlx.get((g.study, g.level), np.nan) if g.phase == "test" else np.nan, **f})
    s.close()
    return pd.DataFrame(rows)


def feature_cols(df):
    return [c for c in df.columns if c.split("_")[0] in MODALITIES and not c.endswith("_z")]


def zscore(df, ref="stimulus"):
    """Add `<feature>_z` per subject and task, using no labels.
    ref="stimulus" (default): centre on baseline 2 (same visual stimulus, no task), scale by the subject's SD over
      all their windows of that task. Removes the luminance confound of the black-screen baseline (pupil) and the
      near-zero resting SD of EMG / rare AUs that blew z-scores up to |z| > 10.
    ref="rest": centre and scale on baseline 1 (5 min black screen), as in the original brief."""
    df = df.drop(columns=[c for c in df.columns if c.endswith("_z")])
    feats = feature_cols(df)
    z = []
    for _, grp in df.groupby(["subject", "study"]):
        lvl = 2 if ref == "stimulus" else 1
        base = grp[(grp.phase == "baseline") & (grp.level == lvl)][feats]
        if base.empty:  # k-drive baseline 2 was not extracted for the first 30 subjects: centre on baseline 1
            base = grp[(grp.phase == "baseline") & (grp.level == 1)][feats]
        sd = grp[feats].std() if ref == "stimulus" else base.std()
        z.append((grp[feats] - base.mean()) / sd.replace(0, np.nan))
    return pd.concat([df, pd.concat(z).add_suffix("_z")], axis=1)


def run(sid, delete_raw=False):
    out_path = FEAT / f"{sid}.parquet"
    if out_path.exists():
        print(sid, "already done")
        return
    t0 = time.time()
    path = download(sid)
    t1 = time.time()
    out = extract(sid)
    FEAT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path)
    if delete_raw:
        path.unlink()
    print(f"{sid}: {len(out)} windows, {len(feature_cols(out))} features | download {t1 - t0:.0f}s, "
          f"extract {time.time() - t1:.0f}s{' | raw deleted' if delete_raw else ''}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--delete-raw", action="store_true", help="delete the HDF5 after extraction")
    a = ap.parse_args()
    for sid in SUBJECTS if a.all else [subject_id(a.subject)]:
        try:
            run(sid, a.delete_raw)
        except Exception as e:  # one bad subject must not stop the loop; it is retried on the next run
            print(f"{sid}: FAILED {e!r}", flush=True)
