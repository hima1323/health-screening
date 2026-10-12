"""ADABase loaders. One subject at a time, one segment at a time (the full SIGNALS table is ~10 GB in RAM).

Layout (public release 0.1.0, 30 subjects, one HDF5 per subject, PyTables blosc:lz4):
  SIGNALS: 1 ms grid. Bio signals (ECG, PPG, EDA, RSP, EMG, SKT) stored at 1000 Hz,
           eye tracker 250 Hz (gaps = NaN), face AUs ~25 Hz, all NaN-padded onto the grid.
  PERFORMANCE / SUBJECTIVE (NASA-TLX) / META: small tables.
n-back test levels 1-3 = 1/2/3-back single task, 4-6 = 1/2/3-back dual task. k-drive test levels 1-3.

    python src/load_adabase.py --subject 0          # print segments of subject 0 (downloads if missing)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tables

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "adabase"
SHARE = "https://owncloud.fraunhofer.de/remote.php/dav/public-files/apCFB5vkibNQAe9/"
SUBJECTS = ["0000-ACAA", "0001-AGDJ", "0002-AHEG", "0003-AZFR", "0004-BDCD", "0005-BQAB", "0006-BRJG",
            "0007-FKDN", "0008-GCAF", "0009-ILAB", "0010-ISJP", "0011-KISN", "0012-KSLI", "0013-KYXT",
            "0014-LEDG", "0015-LINI", "0016-LTRQ", "0017-MDMS", "0018-NMIL", "0019-PFAC", "0020-RLCE",
            "0021-RNDM", "0022-RSBC", "0023-SFKF", "0024-SZLE", "0025-TBMO", "0026-XAPL", "0027-YMAD",
            "0028-ZFML", "0029-ZZOV"]
# segments we extract features from: (study, phase, level)
KEEP = {("n-back", "baseline", 1), ("n-back", "baseline", 2), ("k-drive", "baseline", 1)} \
    | {("n-back", "test", l) for l in range(1, 7)} | {("k-drive", "test", l) for l in range(1, 4)}


def subject_id(s):
    """'0', '0000' or '0000-ACAA' -> '0000-ACAA'."""
    return next(x for x in SUBJECTS if x == s or x.split("-")[0] == f"{int(s):04d}") if s.isdigit() else \
        next(x for x in SUBJECTS if s in x)


def download(sid):
    """Fetch one subject file. Password comes from $ADABASE_PASSWORD, never from the repo."""
    path = RAW / f"{sid}.hdf5"
    if path.exists():
        return path
    pw = os.environ.get("ADABASE_PASSWORD")
    if not pw:
        sys.exit("set ADABASE_PASSWORD (share password) to download")
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    # password via stdin config so it never shows up in `ps`
    subprocess.run(["curl", "-sf", "--retry", "3", "-K", "-", "-o", str(tmp), SHARE + path.name],
                   input=f'user = "public:{pw}"\n', text=True, check=True)
    tmp.rename(path)
    return path


class Subject:
    def __init__(self, sid):
        self.sid = sid
        self.path = RAW / f"{sid}.hdf5"
        self.h5 = tables.open_file(self.path, "r")
        self.t = self.h5.root.SIGNALS.table
        self.cols = list(self.t.attrs.values_block_1_kind)
        self.flag_cols = list(self.t.attrs.values_block_0_kind)

    def close(self):
        self.h5.close()

    def segments(self):
        """DataFrame of contiguous (study, phase, level) runs with row ranges."""
        st = self.t.read(field="values_block_3")
        lv = self.t.read(field="values_block_2")[:, 0]
        key = np.char.add(np.char.add(st[:, 0], st[:, 1]), lv.astype("S2"))
        ch = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1, len(key)]
        return pd.DataFrame([(st[i, 0].decode(), st[i, 1].decode(), int(lv[i]), i, j)
                             for i, j in zip(ch[:-1], ch[1:])],
                            columns=["study", "phase", "level", "start", "stop"])

    def read(self, start, stop):
        """Rows [start, stop) as a DataFrame: t (s from segment start), all signal columns, peak flags."""
        df = pd.DataFrame(self.t.read(start, stop, field="values_block_1"), columns=self.cols)
        df[self.flag_cols] = self.t.read(start, stop, field="values_block_0").astype(bool)
        ts = self.t.read(start, stop, field="index")
        df.insert(0, "t", (ts - ts[0]) / 1000.0)
        return df.replace([np.inf, -np.inf], np.nan)

    def tlx(self):
        """Raw (unweighted) NASA-TLX per (study, level): mean of the six subscales, 0-20 scale."""
        s = pd.read_hdf(self.path, "SUBJECTIVE")
        s["tlx"] = s[["EFFORT", "FRUSTRATION", "MENTAL", "PERFORMANCE", "PHYSICAL", "TEMPORAL"]].mean(axis=1)
        return {(r.STUDY, r.LEVEL): r.tlx for r in s.itertuples()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    sid = subject_id(ap.parse_args().subject)
    download(sid)
    s = Subject(sid)
    seg = s.segments()
    seg["dur_s"] = (seg.stop - seg.start) / 1000
    print(seg[[tuple(r) in KEEP for r in seg[["study", "phase", "level"]].itertuples(index=False)]].to_string())
    print("TLX:", s.tlx())
    s.close()
