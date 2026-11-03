"""Stream selected columns of a data.frame out of a large .RData file without loading the whole frame.

The Yale ED file (560,486 x 972) needs ~4-7 GB through pyreadr; this reader decompresses the gzip stream once per
pass and keeps only the requested columns (numeric vectors are read in bulk with numpy). It implements the parts of
R's XDR serialization format (R Internals, "Serialization Formats") that data frames use; anything else raises.

    columns(path)                 -> [(name, R type, has class/levels), ...]   (pass 1, keeps no data)
    read(path, names)             -> pandas.DataFrame with those columns         (pass 2)
"""
import gzip
import struct

import numpy as np
import pandas as pd

NIL, GLOBALENV, UNBOUND, MISSING, BASENS, NSSXP, PKGSXP, PERSIST = 254, 253, 252, 251, 250, 249, 248, 247
EMPTYENV, BASEENV, ATTRLANG, ATTRLIST, ALTREP, REFSXP = 242, 241, 240, 239, 238, 255
TYPES = {10: "logical", 13: "integer", 14: "double", 16: "character", 19: "list", 9: "charsxp", 1: "symbol",
         2: "pairlist", 24: "raw", 15: "complex"}


class _Reader:
    def __init__(self, path, keep):
        self.f = gzip.open(path, "rb")
        self.keep = keep          # callable(column index) -> bool, used only for the top-level frame's columns
        self.refs = []

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError("truncated .RData stream")
        return b

    def int(self):
        return struct.unpack(">i", self.raw(4))[0]

    def length(self):
        n = self.int()
        if n == -1:
            hi, lo = struct.unpack(">II", self.raw(8))
            n = (hi << 32) + lo
        return n

    def header(self):
        if self.raw(5) not in (b"RDX2\n", b"RDX3\n"):
            raise ValueError("not an XDR .RData file")
        if self.raw(2) != b"X\n":
            raise ValueError("only XDR serialization is supported")
        version = self.int()
        self.int(), self.int()
        if version == 3:
            self.raw(self.int())  # native encoding name

    def item(self, keep_data=True):
        flags = self.int()
        t, has_attr, has_tag = flags & 0xFF, flags & (1 << 9), flags & (1 << 10)
        if t in (NIL, GLOBALENV, UNBOUND, MISSING, BASENS, EMPTYENV, BASEENV):
            return None
        if t == REFSXP:
            idx = flags >> 8
            return self.refs[(idx or self.int()) - 1]
        if t in (PERSIST, PKGSXP, NSSXP):
            raise ValueError(f"unsupported SEXP type {t}")
        if t == 1:                                   # SYMSXP
            s = self.item()
            self.refs.append(s)
            return s
        if t in (2, 6, 17, ATTRLANG, ATTRLIST):      # pairlist-like: walk the CDR chain iteratively
            out, attr = {}, None
            while True:
                if has_attr:
                    attr = self.item()
                tag = self.item() if has_tag else None
                out[tag if tag is not None else len(out)] = self.item()
                flags = self.int()
                t, has_attr, has_tag = flags & 0xFF, flags & (1 << 9), flags & (1 << 10)
                if t == NIL:
                    return out
                if t not in (2, 6, 17, ATTRLANG, ATTRLIST):
                    raise ValueError(f"unexpected CDR type {t}")
        if t == 9:                                   # CHARSXP
            n = self.int()
            return None if n == -1 else self.raw(n).decode("utf-8", "replace")
        if t in (10, 13, 14, 15, 24):
            n = self.length()
            width = {10: 4, 13: 4, 14: 8, 15: 16, 24: 1}[t]
            buf = self.raw(n * width)
            val = None
            if keep_data:
                val = np.frombuffer(buf, {10: ">i4", 13: ">i4", 14: ">f8", 15: ">c16", 24: "u1"}[t]).copy()
            attr = self.item() if has_attr else None
            return {"type": TYPES[t], "data": val, "attr": attr, "n": n}
        if t == 16:                                  # STRSXP
            n = self.length()
            vals = [self.item() for _ in range(n)]
            attr = self.item() if has_attr else None
            return {"type": "character", "data": vals if keep_data else None, "attr": attr, "n": n}
        if t in (19, 20):                            # VECSXP: the data frame itself is the first one met
            n = self.length()
            top = not hasattr(self, "_frame_seen")
            self._frame_seen = True
            vals = [self.item(keep_data=self.keep(i) if top else keep_data) for i in range(n)]
            attr = self.item() if has_attr else None
            return {"type": "list", "data": vals, "attr": attr, "n": n}
        if t == ALTREP:
            info, state, attr = self.item(), self.item(), self.item()
            return {"type": "altrep", "info": info, "state": state, "attr": attr}
        if t == 4:                                   # ENVSXP
            env = {}
            self.refs.append(env)
            self.int()
            env["enclos"], env["frame"], env["hashtab"], env["attr"] = (self.item(), self.item(), self.item(),
                                                                         self.item())
            return env
        raise ValueError(f"unsupported SEXP type {t}")


def _frame(path, keep):
    r = _Reader(path, keep)
    r.header()
    saved = r.item()                                  # pairlist: {object name: object}
    r.f.close()
    (name, df), = [(k, v) for k, v in saved.items() if isinstance(v, dict) and v.get("type") == "list"][:1]
    return df


def columns(path):
    df = _frame(path, keep=lambda i: False)
    names = df["attr"]["names"]["data"]
    return [(n, c["type"], bool(c["attr"] and "levels" in c["attr"])) for n, c in zip(names, df["data"])]


def _to_series(col):
    data, attr = col["data"], col["attr"] or {}
    if "levels" in attr:                              # factor: 1-based codes, NA = INT_MIN
        levels = attr["levels"]["data"]
        codes = np.where(data == np.iinfo(np.int32).min, -1, data - 1)
        return pd.Categorical.from_codes(codes, categories=levels)
    if col["type"] in ("integer", "logical"):
        return pd.array(np.where(data == np.iinfo(np.int32).min, np.nan, data), dtype="Float64").astype("float64")
    if col["type"] == "double":
        return data.astype("float64")                 # R NA/NaN both become NaN
    return data


def read(path, names):
    allnames = [n for n, _, _ in columns(path)]
    want = {allnames.index(n) for n in names}
    df = _frame(path, keep=lambda i: i in want)
    return pd.DataFrame({allnames[i]: _to_series(df["data"][i]) for i in sorted(want)})
