"""P1 measurement agent: heart rate from a contact signal file (ECG or finger PPG), and device readings.

Contact files: CSV (a time column in seconds or a sampling rate, and one signal column) or the MCD-rPPG ECG .json
({"frequency": Hz, "data": [{"title": lead, "values": [...]}]}). Beats are found with a band-pass filter and peak
detection; two readings = the median heart rate of each half (each >= 10 s). Quality = share of regular beat
intervals (within 20% of the median). Source "ecg" or "ppg_contact"; error margins in vital_ranges.yaml.
BP cuff / clip oximeter values are entered as numbers and marked source "device".

    python -m triage.measure.devices <file> [--kind ecg|ppg] [--fs 500] [--column name]
"""
import argparse
import csv
import io
import json
from pathlib import Path

import numpy as np
import yaml
from scipy import signal as sps

from triage.evidence import CONFIG
from triage.measure.spectral import bandpass, halves, ramp

P = yaml.safe_load((CONFIG / "measurement.yaml").read_text(encoding="utf-8"))["contact"]
BANDS = {"ecg": (5.0, 25.0), "ppg": (0.7, 3.5)}


def load(path, fs=None, column=None, lead=None):
    """-> (signal, fs, description)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        d = json.loads(text)
        leads = {x.get("title"): x["values"] for x in d["data"]}
        name = lead if lead in leads else ("II" if "II" in leads else next(iter(leads)))
        return np.asarray(leads[name], float), float(d["frequency"]), f"lead {name}"
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0] if rows and not _is_number(rows[0][0]) else None
    data = np.array([[float(v) if _is_number(v) else np.nan for v in r] for r in rows[1 if header else 0:] if r],
                    float)
    names = header or [f"col{i}" for i in range(data.shape[1])]
    tcol = next((i for i, n in enumerate(names) if n.strip().lower() in ("t", "time", "time_s", "seconds")), None)
    if fs is None:
        if tcol is None:
            raise ValueError("give the sampling rate, or add a time column (seconds) named t / time")
        fs = 1.0 / np.median(np.diff(data[:, tcol]))
    cols = [i for i in range(data.shape[1]) if i != tcol]
    ci = names.index(column) if column in names else cols[0]
    return data[:, ci], float(fs), f"column {names[ci]}"


def _is_number(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def beats(x, fs, kind):
    f = bandpass(x, fs, *BANDS[kind])
    if f is None:
        return None
    if kind == "ecg":                                   # R peaks: pick the polarity with the larger spikes
        f = f if np.percentile(f, 99.5) >= -np.percentile(f, 0.5) else -f
        height = 0.4 * np.percentile(f, 99.5)
    else:
        height = None
    peaks, _ = sps.find_peaks(f, distance=max(1, int(P["plausible_ibi_s"][0] * fs)), height=height,
                              prominence=0.3 * f.std())
    return peaks


def heart_rate(x, fs, kind="ecg"):
    readings, regular, n_beats = [], [], 0
    for a, b in halves(len(x), fs, P["min_half_seconds"]):
        pk = beats(x[a:b], fs, kind)
        if pk is None or len(pk) < 4:
            continue
        ibi = np.diff(pk) / fs
        ibi = ibi[(ibi >= P["plausible_ibi_s"][0]) & (ibi <= P["plausible_ibi_s"][1])]
        if len(ibi) < 3:
            continue
        med = np.median(ibi)
        readings.append(round(60.0 / med, 1))
        regular.append(float(np.mean(np.abs(ibi - med) <= 0.2 * med)))
        n_beats += len(pk)
    source = "ecg" if kind == "ecg" else "ppg_contact"
    if not readings:
        return {"name": "heart_rate", "value": None, "unit": "bpm", "quality": 0.0, "source": source}, \
            {"error": "no regular beats found"}
    q = round(min(ramp(r, *P["regular_share_ramp"]) for r in regular), 2)
    m = {"name": "heart_rate", "value": round(float(np.mean(readings)), 1), "unit": "bpm", "quality": q,
         "source": source}
    if len(readings) >= 2:
        m["repeat_values"] = readings
    return m, {"beats": n_beats, "regular_share": [round(r, 3) for r in regular], "duration_s": round(len(x) / fs, 1)}


def measure(path, kind="ecg", fs=None, column=None):
    x, fs, what = load(path, fs, column)
    m, d = heart_rate(x, fs, kind)
    return m, {**d, "fs": fs, "signal_used": what, "kind": kind,
               "preview": x[: int(min(len(x), 10 * fs))], "preview_fs": fs}


def device_reading(name, readings, unit):
    """A value typed in from a BP cuff or clip oximeter (two readings when available)."""
    readings = [float(r) for r in readings if r is not None]
    m = {"name": name, "value": round(float(np.mean(readings)), 1), "unit": unit, "quality": 0.95, "source": "device"}
    if len(readings) >= 2:
        m["repeat_values"] = readings
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--kind", choices=["ecg", "ppg"], default="ecg")
    ap.add_argument("--fs", type=float)
    ap.add_argument("--column")
    a = ap.parse_args()
    m, d = measure(a.path, a.kind, a.fs, a.column)
    d.pop("preview")
    print(json.dumps({"measurement": m, "diagnostics": d}, indent=1))
