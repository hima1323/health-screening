"""The reasoning model as a small HTTP service: the station sends one capture's feature windows, this runs the
modality agents + fusion model on them and returns the conclusion with the evidence behind it.

Same maths as reasoning_model/src/fusion.py and evidence.py, without their training-time imports (shap, neurokit2):
  agent  = LightGBM on one modality's baseline z-scores -> P(high load), isotonic-calibrated for display
  fusion = non-negative logistic regression on the agents' raw logits -> P(high); the log-odds split exactly into
           per-agent contributions
  SHAP   = LightGBM's own TreeSHAP (pred_contrib), identical to shap.TreeExplainer for these models
The explanation follows reasoner.py's template (no LLM on the server): agents that agree with the label are the
evidence, the others are conflicts, and confidence < 0.6 abstains.

    python model_service/serve.py              # http://127.0.0.1:8001  (MODEL_PORT to move it)
    python model_service/serve.py --check      # self-check on the bundled samples, then exit

POST /predict  {"subject": "<fold id>", "windows": [{"<feature>": value, "q_<modality>": quality, ...}, ...]}
GET  /health
"""
import json
import os
import sys
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MODELS = HERE / "models"
EPS = 1e-3
MIN_CONF = 0.6  # reasoner.MIN_CONF
QUALITY_GATE = 0.5  # train.load masks a modality below this

LABELS = {"ecg": "ECG", "ppg": "Pulse (PPG)", "eda": "Skin conductance", "rsp": "Breathing", "emg": "Muscle (EMG)",
          "skt": "Skin temperature", "eye": "Eye tracker", "au": "Face (action units)"}
# the same sensors as they read inside a sentence
PHRASES = {"ecg": "the ECG", "ppg": "pulse (PPG)", "eda": "skin conductance", "rsp": "breathing",
           "emg": "muscle tension (EMG)", "skt": "skin temperature", "eye": "the eye tracker", "au": "facial expression"}
AU_NAMES = {"01": "inner brow raise", "02": "outer brow raise", "04": "brow lowering", "05": "upper lid raise",
            "06": "cheek raise", "07": "lid tightening", "09": "nose wrinkle", "10": "upper lip raise",
            "11": "nasolabial deepening", "12": "lip corner pull", "14": "dimpling", "15": "lip corner drop",
            "17": "chin raise", "20": "lip stretch", "23": "lip tightening", "24": "lip press", "25": "lips parting",
            "26": "jaw drop", "28": "lip suck", "43": "eyes closing"}
# evidence.FEATURES: name -> (description, unit)
FEATURES = {
    "ecg_hr": ("heart rate", "bpm"), "ecg_rmssd": ("RMSSD heart-rate variability", "ms"),
    "ecg_sdnn": ("SDNN heart-rate variability", "ms"), "ecg_pnn50": ("pNN50 heart-rate variability", "%"),
    "ppg_rate": ("pulse rate", "bpm"), "ppg_amp": ("pulse amplitude", "a.u."), "ppg_ptt": ("pulse transit time", "ms"),
    "eda_tonic": ("tonic skin conductance", "uS"), "eda_scr_count": ("skin conductance responses", "count"),
    "eda_scr_amp": ("skin conductance response amplitude", "uS"), "rsp_rate": ("breathing rate", "/min"),
    "rsp_depth": ("breathing depth", "a.u."), "rsp_var": ("breathing irregularity", "CV"),
    "emg_rms": ("shoulder muscle activity", "a.u."), "skt_mean": ("finger skin temperature", "F"),
    "skt_slope": ("finger skin temperature slope", "F/s"), "eye_pupil_mean": ("pupil diameter", "mm"),
    "eye_pupil_slope": ("pupil diameter slope", "mm/s"), "eye_blink_rate": ("blink rate", "/min"),
    "eye_fix_dur": ("mean fixation duration", "s"),
}
FEATURES.update({f"au_{n}": (f"{name} (facial action unit {n})", "share") for n, name in AU_NAMES.items()})

_bundles = {}


def bundle(subject):
    """The fold model that was trained without `subject` (a file name from models/, never a path)."""
    name = Path(str(subject)).name
    if name not in _bundles:
        path = MODELS / f"{name}.joblib"
        if not path.is_file():
            raise KeyError(f"no model for subject {name!r}")
        _bundles[name] = joblib.load(path)
    return _bundles[name]


def num(x, digits=4):
    return None if x is None or not np.isfinite(x) else float(f"{x:.{digits}g}")


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def predict(subject, windows):
    b = bundle(subject)
    X = pd.DataFrame(windows, dtype=float)
    mods, coef = b["modalities"], b["meta"]["coef"]
    out = [{"agents": [], "logodds": b["meta"]["intercept"]} for _ in range(len(X))]

    for m in mods:
        a = b["agents"][m]
        fs = a["features"]
        Xm = X.reindex(columns=fs)
        q = X.get(f"q_{m}", pd.Series(np.nan, index=X.index))
        Xm[q < QUALITY_GATE] = np.nan  # the quality gate: a weak modality is treated as missing
        ok = Xm.notna().any(axis=1).to_numpy()
        raw = np.full(len(X), np.nan)
        cal = np.full(len(X), np.nan)
        sv = np.zeros((len(X), len(fs)))
        if ok.any():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # sklearn's feature-name warning on DataFrame vs array input
                raw[ok] = a["model"].predict_proba(Xm[ok])[:, 1]
                sv[ok] = a["model"].predict(Xm[ok], pred_contrib=True)[:, :-1]
            cal[ok] = a["iso"].predict(raw[ok])
        for i in range(len(X)):
            avail = bool(ok[i])
            contrib = (logit(raw[i]) * coef[m] if avail else 0.0) + (coef[f"avail_{m}"] if avail else 0.0)
            out[i]["logodds"] += contrib
            rep = {"modality": m, "label": LABELS[m], "available": avail, "quality": num(q.iloc[i]),
                   "weight": num(coef[m]), "contribution": num(contrib)}
            if avail:
                order = np.argsort(-np.abs(sv[i]))[:3]
                rep.update(probability_high=num(cal[i]), says="high" if cal[i] >= 0.5 else "low",
                           top_features=[feature(fs[j], X.iloc[i], sv[i, j]) for j in order
                                         if np.isfinite(Xm.iloc[i, j])])
            out[i]["agents"].append(rep)

    recs = [window_record(r) for r in out]
    p = float(np.mean([r["probability_high"] for r in recs]))
    label = "high" if p >= 0.5 else "low"
    return {"subject": b["test_subject"], "trained_on_subjects": len(b["train_subjects"]), "windows": recs,
            "summary": summary(recs, label, p), "vitals": vitals(X)}


def vitals(X):
    """Plain readings from the same capture, for the report: means over the windows that measured them."""
    def mean(col, gate):
        if col not in X:
            return None
        ok = X[col].where(X.get(f"q_{gate}", 1) >= QUALITY_GATE)
        return num(ok.mean(), 3) if ok.notna().any() else None
    skin_f = mean("skt_mean", "skt")
    return {"heartRate": mean("ecg_hr", "ecg"), "breathingRate": mean("rsp_rate", "rsp"),
            "skinTempC": None if skin_f is None else num((skin_f - 32) / 1.8, 3)}


def feature(k, row, shap):
    name = k[:-2]  # '<name>_z'
    desc, unit = FEATURES[name]
    return {"feature": name, "description": desc, "unit": unit, "value": num(row.get(name, np.nan)),
            "z": num(row.get(k, np.nan), 3), "shap": num(shap, 3), "pushes_toward": "high" if shap > 0 else "low"}


def window_record(r):
    p = float(1 / (1 + np.exp(-r["logodds"])))
    label = "high" if p >= 0.5 else "low"
    conf = p if label == "high" else 1 - p
    av = sorted([a for a in r["agents"] if a["available"]], key=lambda a: -abs(a["contribution"]))
    return {"label": label, "probability_high": num(p), "confidence": num(conf), "agents": r["agents"],
            "support": [a["modality"] for a in av if a["says"] == label],
            "conflict": [a["modality"] for a in av if a["says"] != label],
            "abstain": conf < MIN_CONF}


def summary(recs, label, p):
    """The capture as a whole: mean P(high) over its windows, and which agents pushed it which way."""
    conf = p if label == "high" else 1 - p
    agents = {}
    for r in recs:
        for a in r["agents"]:
            s = agents.setdefault(a["modality"], {"modality": a["modality"], "label": a["label"], "contribution": 0.0,
                                                  "windows": 0})
            if a["available"]:
                s["contribution"] += a["contribution"] / len(recs)
                s["windows"] += 1
    agents = sorted(agents.values(), key=lambda a: -abs(a["contribution"]))
    for a in agents:
        a["contribution"] = num(a["contribution"], 3)
    used = [a for a in agents if a["windows"]]
    lead = [a for a in used if (a["contribution"] > 0) == (label == "high")][:3]
    against = [a for a in used if (a["contribution"] > 0) != (label == "high")][:2]
    top = max((f for r in recs for a in r["agents"] if a["available"] and a["modality"] == lead[0]["modality"]
               for f in a["top_features"][:1]), key=lambda f: abs(f["shap"] or 0), default=None) if lead else None

    abstain = conf < MIN_CONF
    level = {"high": "high", "low": "low"}[label]
    text = (f"The model is not sure about this capture ({round(conf * 100)}% confidence), so it makes no call."
            if abstain else
            f"The model reads {level} mental load, {round(conf * 100)}% confidence, over {len(recs)} windows of 30 s.")
    if lead:
        text += " Most of the push came from " + join([PHRASES[a["modality"]] for a in lead]) + "."
    if top:
        text += f" The strongest single sign was {top['description']} at {top['z']:+.1f} SD from this person's rest level."
    if against:
        text += " Pointing the other way: " + join([PHRASES[a["modality"]] for a in against]) + "."
    return {"label": label, "probability_high": num(p), "confidence": num(conf), "abstain": abstain,
            "agents": agents, "explanation": text, "windows": len(recs)}


def join(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ok": True, "models": sorted(p.stem for p in MODELS.glob("*.joblib"))})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/predict":
            return self.reply(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length", 0))
            if size > 2_000_000:
                return self.reply(413, {"error": "capture too large"})
            body = json.loads(self.rfile.read(size))
            windows = body["windows"]
            if not isinstance(windows, list) or not 0 < len(windows) <= 200:
                return self.reply(400, {"error": "windows must be a list of 1-200 feature windows"})
            self.reply(200, predict(body["subject"], windows))
        except KeyError as err:
            self.reply(400, {"error": f"missing or unknown {err}"})
        except (ValueError, TypeError) as err:
            self.reply(400, {"error": str(err)})

    def log_message(self, fmt, *args):
        sys.stderr.write("model: " + fmt % args + "\n")


def exit_with_parent():
    """Started by the Node server: if it dies without stopping us (kill -9), don't linger on the port."""
    parent = os.getppid()
    while os.getppid() == parent:
        time.sleep(2)
    os._exit(0)


def check():
    """Every bundled sample reproduces fusion.py's own out-of-fold probabilities, window by window."""
    for path in sorted((HERE / "samples").glob("*.json")):
        s = json.loads(path.read_text())
        r = predict(s["subject"], s["windows"])
        got = [w["probability_high"] for w in r["windows"]]
        assert np.allclose(got, s["fusion_py_probability_high"], atol=1e-3), (path.name, got)
        print(f"ok  {path.stem}: {r['summary']['label']} {r['summary']['confidence']} — "
              f"{r['summary']['explanation'][:80]}…")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        port = int(os.environ.get("MODEL_PORT", 8001))
        for path in MODELS.glob("*.joblib"):  # load up front, so the first scan isn't the slow one
            bundle(path.stem)
        print(f"model service on http://127.0.0.1:{port} ({len(_bundles)} models)", flush=True)
        threading.Thread(target=exit_with_parent, daemon=True).start()
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
