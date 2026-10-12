"""Modality agents + fusion model (late fusion / stacking), leave-one-subject-out.

Agent = one LightGBM per modality (ECG, PPG, EDA, RSP, EMG, SKT, eye, AU) on that modality's features only:
  P(high load), isotonic-calibrated, plus SHAP over its own features. A window where the modality is missing or
  below the quality gate has no agent output (the agent is "unavailable").
Fusion = logistic regression on the agents' logits (0 when unavailable) and availability flags, trained on
  inner out-of-fold agent outputs so it never sees in-sample (overconfident) agent probabilities.
  Its log-odds split exactly into per-agent contributions (weight x logit), which the reasoner can cite.
New sensors (rPPG, thermal, EEG) become new agents that can be pretrained on single-modality datasets.

Outputs: results/oof_fusion.parquet, results/oof_fusion_kdrive.parquet, results/models/fusion/<subject>.joblib

    python src/fusion.py                  # all subjects
    python src/fusion.py --subject 3      # one fold (debug, not saved)
"""
import argparse

import joblib
import numpy as np
import pandas as pd
import shap
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression

from features import MODALITIES
from load_adabase import subject_id
from train import RES, inner_cv, kdrive_rows, learned_rules, load, make, modality, task_rows

EPS = 1e-3


class NonNegLogit:
    """Logistic regression whose agent-logit weights are >= 0 (availability flags and intercept free), L2 = lam.
    A negative weight would read as "EDA says high, so lean low", which no explanation can justify."""

    def __init__(self, lam=1.0):
        self.lam = lam

    def fit(self, Z, y):
        X, y = np.c_[Z.to_numpy(), np.ones(len(Z))], np.asarray(y, float)
        k = Z.shape[1]
        bounds = [(0, None) if not c.startswith("avail_") else (None, None) for c in Z.columns] + [(None, None)]

        def f(w):
            z = X @ w
            p = expit(z)
            loss = np.sum(np.logaddexp(0, z) - y * z) + 0.5 * self.lam * w[:k] @ w[:k]
            grad = X.T @ (p - y) + self.lam * np.r_[w[:k], 0]
            return loss, grad
        w = minimize(f, np.zeros(k + 1), jac=True, bounds=bounds, method="L-BFGS-B").x
        self.coef_, self.intercept_ = w[None, :k], w[k:]
        return self

    def predict_proba(self, Z):
        p = expit(Z.to_numpy() @ self.coef_[0] + self.intercept_[0])
        return np.c_[1 - p, p]


def agent_feats(feats):
    return {m: [c for c in feats if modality(c) == m] for m in MODALITIES if any(modality(c) == m for c in feats)}


def meta_X(probs, mods):
    """probs: DataFrame of raw agent P(high) (NaN = unavailable) -> fusion inputs [logit_m..., avail_m...]."""
    lg = logit(probs[mods].clip(EPS, 1 - EPS)).fillna(0.0)
    av = probs[mods].notna().astype(float).add_prefix("avail_")
    return pd.concat([lg, av], axis=1)


def fit_fold(df, feats, test_sid, seed=0):
    rows, y = task_rows(df, "binary")
    tr = rows.subject != test_sid
    groups = rows.loc[tr, "subject"]
    agents, oof = {}, pd.DataFrame(index=rows.index[tr])
    for m, fs in agent_feats(feats).items():
        X, yt = rows.loc[tr, fs], y[tr]
        avail = X.notna().any(axis=1)
        p, n_est, _ = inner_cv(X[avail], yt[avail], groups[avail], "binary", {}, seed, dropout=False)
        model = make("binary", {}, n_est, seed).fit(X[avail], yt[avail])
        agents[m] = {"model": model, "features": fs, "n_estimators": n_est,
                     "iso": IsotonicRegression(out_of_bounds="clip").fit(p, yt[avail]),
                     "rules": learned_rules(X, yt)}
        oof[m] = np.nan
        oof.loc[avail[avail].index, m] = p
    mods = list(agents)
    Z = meta_X(oof, mods)
    nn = NonNegLogit().fit(Z, y[tr])
    meta = {"coef": dict(zip(Z.columns, nn.coef_[0])), "intercept": float(nn.intercept_[0])}  # plain dict: portable
    return {"agents": agents, "meta": meta, "modalities": mods, "ref": df.attrs.get("ref"),
            "test_subject": test_sid, "train_subjects": sorted(set(groups))}


def agent_probs(bundle, X):
    """Raw and calibrated P(high) per agent (NaN where the modality is unavailable)."""
    raw, cal = pd.DataFrame(index=X.index), pd.DataFrame(index=X.index)
    for m, a in bundle["agents"].items():
        Xm = X[a["features"]]
        ok = Xm.notna().any(axis=1)
        raw[m] = cal[m] = np.nan
        if ok.any():
            p = a["model"].predict_proba(Xm[ok])[:, 1]
            raw.loc[ok, m], cal.loc[ok, m] = p, a["iso"].predict(p)
    return raw, cal


def fuse(bundle, raw):
    """Fused P(high) and the exact per-agent log-odds contributions."""
    mods, meta = bundle["modalities"], bundle["meta"]
    Z = meta_X(raw, mods)
    w = pd.Series(meta["coef"])[Z.columns]
    contrib = pd.DataFrame({m: Z[m] * w[m] + Z[f"avail_{m}"] * w[f"avail_{m}"] for m in mods}, index=Z.index)
    return expit(contrib.sum(axis=1).to_numpy() + meta["intercept"]), contrib


def predict_rows(bundle, X, save_shap):
    raw, cal = agent_probs(bundle, X)
    prob, contrib = fuse(bundle, raw)
    out = pd.DataFrame({"prob": prob}, index=X.index)
    out[[f"agent_{m}" for m in cal]] = cal.to_numpy()
    out[[f"contrib_{m}" for m in contrib]] = contrib.to_numpy()
    if save_shap:
        for m, a in bundle["agents"].items():
            sv = shap.TreeExplainer(a["model"]).shap_values(X[a["features"]])
            sv = sv[1] if isinstance(sv, list) else sv
            out[[f"shap_{c}" for c in a["features"]]] = sv
    return out


def loso(df, feats, subjects=None, save=True):
    rows, y = task_rows(df, "binary")
    out, kd_out = [], []
    for sid in subjects or sorted(rows.subject.unique()):
        b = fit_fold(df, feats, sid)
        te = rows.subject == sid
        res = rows.loc[te, ["subject", "study", "phase", "level", "nback_n", "dual", "win_start"]].copy()
        res["y"] = y[te].to_numpy()
        out.append(pd.concat([res, predict_rows(b, rows.loc[te, feats], save)], axis=1))
        kd, ky = kdrive_rows(df[df.subject == sid])
        if len(kd):
            k = kd[["subject", "study", "phase", "level", "win_start"]].copy()
            k["y"] = ky.to_numpy()
            kd_out.append(pd.concat([k, predict_rows(b, kd[feats], False)], axis=1))
        if save:
            (RES / "models" / "fusion").mkdir(parents=True, exist_ok=True)
            joblib.dump(b, RES / "models" / "fusion" / f"{sid}.joblib")
        print(sid, "weights", {m: round(b["meta"]["coef"][m], 2) for m in b["modalities"]}, flush=True)
    oof, kd = pd.concat(out, ignore_index=True), pd.concat(kd_out, ignore_index=True)
    if save:
        oof.to_parquet(RES / "oof_fusion.parquet")
        kd.to_parquet(RES / "oof_fusion_kdrive.parquet")
    return oof, kd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", help="run a single LOSO fold")
    ap.add_argument("--ref", default="stimulus", choices=["stimulus", "rest"])
    a = ap.parse_args()
    df, feats = load(a.ref)
    oof, kd = loso(df, feats, [subject_id(a.subject)] if a.subject else None, save=not a.subject)
    from evaluate import binary_metrics
    rows = [{"model": "fusion", "set": "n-back LOSO", **binary_metrics(oof.y, oof.prob)},
            {"model": "fusion", "set": "k-drive cross-task", **binary_metrics(kd.y, kd.prob)}]
    for c in [c for c in oof.columns if c.startswith("agent_")]:
        ok = oof[c].notna()
        rows.append({"model": c, "set": f"n-back LOSO ({ok.mean():.0%} available)", **binary_metrics(oof.y[ok], oof[c][ok])})
    r = pd.DataFrame(rows)
    r.insert(2, "subjects", oof.subject.nunique())
    print(r.round(3).to_string())
    if not a.subject:
        r.to_csv(RES / "fusion_metrics.csv", index=False)
