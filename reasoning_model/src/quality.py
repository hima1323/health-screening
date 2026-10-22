"""Per-window signal-quality indices, each in [0, 1] (1 = clean). Cheap heuristics, not learned.

    python src/quality.py --subject 0     # quality summary from the subject's feature parquet
"""
import argparse

import numpy as np


def beats(peak_times, lo=0.3, hi=2.0, jump=0.2):
    """Share of inter-beat intervals that are plausible (lo..hi s) and change < `jump` from the previous one."""
    ibi = np.diff(peak_times)
    if len(ibi) < 3:
        return 0.0
    ok = (ibi > lo) & (ibi < hi)
    ok[1:] &= np.abs(np.diff(ibi)) / ibi[:-1] < jump
    return float(ok.mean())


def breaths(peak_times):
    """Share of breath intervals between 1.5 s and 15 s (4-40 breaths/min)."""
    return beats(peak_times, lo=1.5, hi=15.0, jump=1.0)


def coverage(x, expected_n):
    """Share of expected samples present and finite."""
    return float(min(np.isfinite(x).sum() / expected_n, 1.0)) if expected_n else 0.0


def smooth(x):
    """0 if flat (disconnected), else 1 - share of first differences > 10x their median (jump artifacts)."""
    x = x[np.isfinite(x)]
    if len(x) < 10 or np.ptp(x) == 0:
        return 0.0
    d = np.abs(np.diff(x))
    return float(1 - (d > 10 * np.median(d[d > 0])).mean())


if __name__ == "__main__":
    import pandas as pd
    from load_adabase import subject_id
    from features import FEAT

    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    df = pd.read_parquet(FEAT / f"{subject_id(ap.parse_args().subject)}.parquet")
    print(df.filter(like="q_").describe().T[["mean", "min", "50%"]])
