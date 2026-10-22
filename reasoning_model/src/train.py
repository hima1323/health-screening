"""LightGBM predictor, leave-one-subject-out, isotonic calibration, SHAP, cross-task test on k-drive.

Tasks (n-back only for training; k-drive held out entirely):
  binary : low = 1-back, high = 2-back / 3-back (single + dual task)
           (with --ref rest, baseline 2 is also low, as in the brief; with the default --ref stimulus it is the
           normalisation reference and cannot also be a training sample)
  3class : 1-back / 2-back / 3-back
  tlx    : raw NASA-TLX of the run (regression)
Inputs are per-subject z-scored features (features.zscore); a modality is masked when its quality < 0.5.

Per held-out subject, a 5-fold subject-wise inner CV over the training subjects gives
  - the Optuna objective (--tune), - the number of trees (median early-stopping iteration),
  - out-of-fold probabilities for the isotonic calibrator (so calibration never sees its own training data).
The final fold model is refit on all training subjects. Outputs: results/oof_<task>.parquet (+ oof_kdrive.parquet),
results/models/<task>/<subject>.joblib (model, calibrator, features, learned rule directions, params).

    python src/train.py --task binary [--tune] [--ref stimulus|rest]
    python src/train.py --task binary --subject 3     # one fold only (debug)
"""
import argparse
import json
import warnings

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
import shap
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from features import FEAT, MODALITIES, zscore
from load_adabase import ROOT, subject_id

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)
RES = ROOT / "results"
BASE = dict(num_leaves=15, learning_rate=0.03, min_child_samples=20, colsample_bytree=0.7, verbose=-1, n_jobs=4)
DROP_P = 0.3  # share of training windows with one whole modality removed
INNER, TRIALS = 5, 25


def modality(col):
    return col.split("_")[0]


def load(ref="stimulus"):
    df = zscore(pd.concat([pd.read_parquet(p) for p in sorted(FEAT.glob("*.parquet"))], ignore_index=True), ref)
    df.attrs["ref"] = ref
    feats = [c for c in df.columns if c.endswith("_z")]
    for m in MODALITIES:  # quality gate
        q = df.get(f"q_{m}")
        if q is not None:
            df.loc[q < 0.5, [c for c in feats if modality(c) == m]] = np.nan
    df[feats] = df[feats].replace([np.inf, -np.inf], np.nan)
    return df, feats


def task_rows(df, task):
    test = (df.study == "n-back") & (df.phase == "test")
    if df.attrs.get("ref") == "rest":
        test |= (df.study == "n-back") & (df.phase == "baseline") & (df.level == 2)
    nb = df[test]
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
    cols = {m: [j for j, c in enumerate(X.columns) if modality(c) == m] for m in mods}
    for i in np.flatnonzero(rng.random(len(X)) < DROP_P):
        X.iloc[i, cols[mods[rng.integers(len(mods))]]] = np.nan
    return X


def learned_rules(X, y):
    """Expected direction of each feature under high load, from training subjects: sign of mean z difference."""
    d = X[y == 1].mean() - X[y == 0].mean()
    return {c: (int(np.sign(v)) if abs(v) > 0.1 else 0) for c, v in d.items() if np.isfinite(v)}


def make(task, params, n_estimators, seed):
    p = {**BASE, **params, "n_estimators": n_estimators, "random_state": seed}
    return lgb.LGBMRegressor(**p) if task == "tlx" else lgb.LGBMClassifier(**p, class_weight="balanced")


def scores(task, model, X):
    return model.predict_proba(X)[:, 1] if task == "binary" else \
        model.predict_proba(X) if task == "3class" else model.predict(X)


def inner_cv(X, y, groups, task, params, seed, dropout=True):
    """Subject-wise inner CV with early stopping. Returns OOF scores, median best iteration, CV loss (lower=better)."""
    oof = np.zeros((len(X), 3)) if task == "3class" else np.zeros(len(X))
    iters = []
    rng = np.random.default_rng(seed)
    for tr, va in GroupKFold(INNER).split(X, y, groups):
        m = make(task, params, 500, seed)
        m.fit(modality_dropout(X.iloc[tr], rng) if dropout else X.iloc[tr], y.iloc[tr], eval_set=[(X.iloc[va], y.iloc[va])],
              callbacks=[lgb.early_stopping(50, verbose=False)])
        oof[va] = scores(task, m, X.iloc[va])
        iters.append(m.best_iteration_ or 500)
    if task == "binary":
        loss = -roc_auc_score(y, oof)
    elif task == "3class":
        loss = -np.mean(oof.argmax(1) == y.to_numpy())
    else:
        loss = np.mean(np.abs(oof - y.to_numpy()))
    return oof, int(np.median(iters)), loss


def tune(X, y, groups, task, seed):
    def objective(trial):
        p = {"num_leaves": trial.suggest_int("num_leaves", 4, 31),
             "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
             "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
             "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
             "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10, log=True)}
        return inner_cv(X, y, groups, task, p, seed)[2]
    study = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=seed))
    study.enqueue_trial({k: BASE[k] for k in ["num_leaves", "learning_rate", "min_child_samples",
                                               "colsample_bytree"]} | {"reg_lambda": 1e-3})
    study.optimize(objective, n_trials=TRIALS)
    return study.best_params


def fit_fold(df, feats, task, test_sid, do_tune=False, seed=0):
    rows, y = task_rows(df, task)
    tr = rows.subject != test_sid
    X, yt, g = rows.loc[tr, feats], y[tr], rows.loc[tr, "subject"]
    params = tune(X, yt, g, task, seed) if do_tune else {}
    oof, n_est, _ = inner_cv(X, yt, g, task, params, seed)
    model = make(task, params, n_est, seed).fit(modality_dropout(X, np.random.default_rng(seed)), yt)
    iso = IsotonicRegression(out_of_bounds="clip").fit(oof, yt) if task == "binary" else None
    return {"model": model, "iso": iso, "features": feats, "params": params, "n_estimators": n_est,
            "rules": learned_rules(X, yt) if task == "binary" else None, "ref": df.attrs.get("ref"),
            "test_subject": test_sid, "train_subjects": sorted(set(g))}


def predict(bundle, X):
    """Calibrated probability of high load (binary), class (3class) or score (tlx)."""
    m = bundle["model"]
    if bundle["iso"] is not None:
        return bundle["iso"].predict(m.predict_proba(X)[:, 1])
    return m.predict(X)


def loso(df, feats, task, subjects=None, save=True, do_tune=False):
    rows, y = task_rows(df, task)
    out, kd_out = [], []
    for sid in subjects or sorted(rows.subject.unique()):
        b = fit_fold(df, feats, task, sid, do_tune)
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
        if do_tune:
            print(sid, json.dumps(b["params"]), b["n_estimators"], flush=True)
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
    ap.add_argument("--tune", action="store_true", help="Optuna inside the subject-wise inner CV")
    ap.add_argument("--ref", default="stimulus", choices=["stimulus", "rest"])
    a = ap.parse_args()
    df, feats = load(a.ref)
    subs = [subject_id(a.subject)] if a.subject else None
    oof, kd = loso(df, feats, a.task, subs, save=not a.subject, do_tune=a.tune)
    print(f"{a.task} (ref={a.ref}, tune={a.tune}): {oof.subject.nunique()} subjects, {len(oof)} windows, "
          f"{len(feats)} features")
    from evaluate import summarize
    print(summarize(oof, a.task, kd).to_string())
