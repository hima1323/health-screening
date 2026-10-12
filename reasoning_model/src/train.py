"""LightGBM predictor, leave-one-subject-out, isotonic calibration, SHAP, cross-task test on k-drive.

Tasks (n-back only for training; k-drive held out entirely):
  binary : low = baseline-2 / 1-back, high = 2-back / 3-back (single + dual task)
  3class : 1-back (incl. baseline-2) / 2-back / 3-back
  tlx    : raw NASA-TLX of the run (regression)
Inputs are baseline z-scored features only; a modality is masked (NaN) in windows where its quality < 0.5.

Per held-out subject: training subjects are split 80/20 by subject; the 20% drives early stopping and the
isotonic calibrator. Outputs: results/oof_<task>.parquet (+ results/oof_kdrive.parquet for binary),
results/models/<task>/<subject>.joblib (model, calibrator, features, learned rule directions).

    python src/train.py --task binary              # all subjects, LOSO
    python src/train.py --task binary --subject 3  # one fold only (debug)
"""
import argparse
import warnings

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.isotonic import IsotonicRegression

from features import FEAT, MODALITIES
from load_adabase import ROOT, subject_id

warnings.filterwarnings("ignore")
RES = ROOT / "results"
PARAMS = dict(num_leaves=15, learning_rate=0.03, n_estimators=500, min_child_samples=20,
              colsample_bytree=0.7, class_weight="balanced", verbose=-1, n_jobs=4)
DROP_P = 0.3  # share of training windows with one whole modality removed


def modality(col):
    return col.split("_")[0]


def load():
    df = pd.concat([pd.read_parquet(p) for p in sorted(FEAT.glob("*.parquet"))], ignore_index=True)
    feats = [c for c in df.columns if c.endswith("_z")]
    for m in MODALITIES:  # quality gate
        q = df.get(f"q_{m}")
        if q is not None:
            df.loc[q < 0.5, [c for c in feats if modality(c) == m]] = np.nan
    df[feats] = df[feats].replace([np.inf, -np.inf], np.nan)
    return df, feats


def task_rows(df, task):
    nb = df[(df.study == "n-back") & ((df.phase == "test") | ((df.phase == "baseline") & (df.level == 2)))]
    if task == "binary":
        return nb, (nb.nback_n >= 2).astype(int)
    if task == "3class":
        return nb, nb.nback_n.clip(lower=1) - 1
    nb = nb[nb.tlx.notna()]
    return nb, nb.tlx


def kdrive_rows(df):
    kd = df[(df.study == "k-drive") & (df.phase == "test")]
    return kd, (kd.level >= 2).astype(int)  # level 1 = driving only, 2-3 = added secondary tasks


def modality_dropout(X, rng):
    X = X.copy()
    mods = sorted({modality(c) for c in X.columns})
    for i in np.flatnonzero(rng.random(len(X)) < DROP_P):
        m = mods[rng.integers(len(mods))]
        X.iloc[i, [j for j, c in enumerate(X.columns) if modality(c) == m]] = np.nan
    return X


def learned_rules(X, y):
    """Expected direction of each feature under high load, from training subjects: sign of mean z difference."""
    d = X[y == 1].mean() - X[y == 0].mean()
    return {c: (int(np.sign(v)) if abs(v) > 0.1 else 0) for c, v in d.items() if np.isfinite(v)}


def fit_fold(df, feats, task, test_sid, seed=0):
    rng = np.random.default_rng(seed)
    rows, y = task_rows(df, task)
    train_sids = sorted(set(rows.subject) - {test_sid})
    cal_sids = set(rng.choice(train_sids, max(1, len(train_sids) // 5), replace=False))
    fit = ~rows.subject.isin(cal_sids | {test_sid})
    cal = rows.subject.isin(cal_sids)

    Xf = modality_dropout(rows.loc[fit, feats], rng)
    if task == "tlx":
        model = lgb.LGBMRegressor(**{k: v for k, v in PARAMS.items() if k != "class_weight"}, random_state=seed)
    else:
        model = lgb.LGBMClassifier(**PARAMS, random_state=seed)
    model.fit(Xf, y[fit], eval_set=[(rows.loc[cal, feats], y[cal])],
              callbacks=[lgb.early_stopping(50, verbose=False)])
    iso = None
    if task == "binary":
        # ponytail: early stopping and calibration share the calibration subjects; split them if ECE looks optimistic
        iso = IsotonicRegression(out_of_bounds="clip").fit(model.predict_proba(rows.loc[cal, feats])[:, 1], y[cal])
    rules = learned_rules(rows.loc[~rows.subject.eq(test_sid), feats], y[~rows.subject.eq(test_sid)]) \
        if task == "binary" else None
    return {"model": model, "iso": iso, "features": feats, "rules": rules, "test_subject": test_sid,
            "train_subjects": train_sids}


def predict(bundle, X):
    """Calibrated probability of high load (binary), class (3class) or score (tlx)."""
    m = bundle["model"]
    if bundle["iso"] is not None:
        return bundle["iso"].predict(m.predict_proba(X)[:, 1])
    return m.predict(X)


def loso(df, feats, task, subjects=None, save=True):
    rows, y = task_rows(df, task)
    out, kd_out = [], []
    for sid in subjects or sorted(rows.subject.unique()):
        b = fit_fold(df, feats, task, sid)
        te = rows.subject == sid
        res = rows.loc[te, ["subject", "study", "phase", "level", "nback_n", "dual", "win_start"]].copy()
        res["y"] = y[te].to_numpy()
        if task == "binary":
            res["prob_raw"] = b["model"].predict_proba(rows.loc[te, feats])[:, 1]
            res["prob"] = predict(b, rows.loc[te, feats])
            if save:
                sv = shap.TreeExplainer(b["model"]).shap_values(rows.loc[te, feats])
                sv = sv[1] if isinstance(sv, list) else sv
                res[[f"shap_{c}" for c in feats]] = sv
            kd, ky = kdrive_rows(df[df.subject == sid])
            if len(kd):
                k = kd[["subject", "study", "phase", "level", "win_start"]].copy()
                k["y"], k["prob"] = ky.to_numpy(), predict(b, kd[feats])
                kd_out.append(k)
        else:
            res["pred"] = predict(b, rows.loc[te, feats])
        out.append(res)
        if save:
            (RES / "models" / task).mkdir(parents=True, exist_ok=True)
            joblib.dump(b, RES / "models" / task / f"{sid}.joblib")
    oof = pd.concat(out, ignore_index=True)
    kd = pd.concat(kd_out, ignore_index=True) if kd_out else None
    if save:
        oof.to_parquet(RES / f"oof_{task}.parquet")
        if kd is not None:
            kd.to_parquet(RES / "oof_kdrive.parquet")
    return oof, kd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="binary", choices=["binary", "3class", "tlx"])
    ap.add_argument("--subject", help="run a single LOSO fold")
    a = ap.parse_args()
    df, feats = load()
    subs = [subject_id(a.subject)] if a.subject else None
    oof, kd = loso(df, feats, a.task, subs, save=not a.subject)
    print(f"{a.task}: {oof.subject.nunique()} subjects, {len(oof)} windows, {len(feats)} features")
    from evaluate import summarize
    print(summarize(oof, a.task, kd).to_string())
