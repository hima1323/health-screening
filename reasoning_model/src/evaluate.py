"""Metrics, ablations, calibration and explanation faithfulness. Tables -> results/*.csv, figures -> results/*.png.

    python src/evaluate.py                 # metrics from saved OOF files + faithfulness + reasoner stats
    python src/evaluate.py --ablations     # also retrain LOSO for every modality subset (slower)
    python src/evaluate.py --subject 0     # per-subject metrics only
"""
import argparse
import json

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score

from features import MODALITIES
from load_adabase import subject_id
from train import RES, load, loso, modality, predict

TOPK = 3  # features removed in the faithfulness test


def ece(y, p, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(y[idx == b].mean() - p[idx == b].mean()) * (idx == b).mean()
                     for b in range(bins) if (idx == b).any()))


def binary_metrics(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return {"bal_acc": balanced_accuracy_score(y, p >= 0.5), "macro_f1": f1_score(y, p >= 0.5, average="macro"),
            "auroc": roc_auc_score(y, p) if len(set(y)) > 1 else np.nan, "ece": ece(y, p)}


def summarize(oof, task, kd=None):
    n = {"subjects": oof.subject.nunique(), "windows": len(oof)}
    if task == "binary":
        rows = [{"set": "n-back LOSO", **n, **binary_metrics(oof.y, oof.prob)},
                {"set": "n-back LOSO (uncalibrated)", **n, **binary_metrics(oof.y, oof.prob_raw)}]
        if kd is not None:
            rows.append({"set": "k-drive cross-task", "subjects": kd.subject.nunique(), "windows": len(kd),
                         **binary_metrics(kd.y, kd.prob)})
        return pd.DataFrame(rows)
    if task == "3class":
        return pd.DataFrame([{**n, "bal_acc": balanced_accuracy_score(oof.y, oof.pred),
                              "macro_f1": f1_score(oof.y, oof.pred, average="macro")}])
    rho = oof.groupby("subject").apply(lambda g: spearmanr(g.y, g.pred)[0]).mean()
    return pd.DataFrame([{**n, "mae": (oof.y - oof.pred).abs().mean(), "spearman_all": spearmanr(oof.y, oof.pred)[0],
                          "spearman_within_subject": rho}])


def ablations():
    df, feats = load()
    sets = {"all": feats,
            "contact": [c for c in feats if MODALITIES[modality(c)] == "contact"],
            "contactless (eye+AU)": [c for c in feats if MODALITIES[modality(c)] == "contactless"]}
    for m in MODALITIES:
        sets[f"only {m}"] = [c for c in feats if modality(c) == m]
        sets[f"all minus {m}"] = [c for c in feats if modality(c) != m]
    rows = []
    for name, fs in sets.items():
        oof, kd = loso(df, fs, "binary", save=False)
        r = summarize(oof, "binary", kd).set_index("set")
        rows.append({"features": name, "n_features": len(fs), "subjects": r.loc["n-back LOSO", "subjects"],
                     "windows": r.loc["n-back LOSO", "windows"],
                     **r.loc["n-back LOSO", ["bal_acc", "macro_f1", "auroc", "ece"]].add_prefix("nback_"),
                     **r.loc["k-drive cross-task", ["bal_acc", "auroc"]].add_prefix("kdrive_")})
        print(rows[-1], flush=True)
    # majority-class baseline
    oof = pd.read_parquet(RES / "oof_binary.parquet")
    maj = oof.groupby("subject").y.transform(lambda s: oof[oof.subject != s.name].y.mode()[0])
    rows.append({"features": "majority class", "n_features": 0, "subjects": oof.subject.nunique(),
                 "windows": len(oof), "nback_bal_acc": balanced_accuracy_score(oof.y, maj),
                 "nback_macro_f1": f1_score(oof.y, maj, average="macro"), "nback_auroc": 0.5})
    pd.DataFrame(rows).to_csv(RES / "ablations.csv", index=False)


def faithfulness():
    """Remove (NaN) the top-k SHAP features supporting the prediction; the probability should move toward the
    other class more than when removing k random available features."""
    df, feats = load()
    oof = pd.read_parquet(RES / "oof_binary.parquet")
    rng = np.random.default_rng(0)
    rows = []
    for sid, g in oof.groupby("subject"):
        b = joblib.load(RES / "models" / "binary" / f"{sid}.joblib")
        X = df.loc[df.subject == sid].set_index(["study", "phase", "level", "win_start"]) \
            .loc[list(g[["study", "phase", "level", "win_start"]].itertuples(index=False, name=None)), feats]
        X = X.reset_index(drop=True)
        sv = g[[f"shap_{c}" for c in feats]].to_numpy()
        sign = np.where(g.prob.to_numpy() >= 0.5, 1, -1)
        for i in range(len(X)):
            avail = np.flatnonzero(X.iloc[i].notna().to_numpy())
            support = [j for j in np.argsort(-sv[i] * sign[i]) if j in avail and sv[i, j] * sign[i] > 0][:TOPK]
            if len(support) < TOPK:
                continue
            base = predict(b, X.iloc[[i]])[0]
            cut, rnd = X.iloc[[i]].copy(), X.iloc[[i]].copy()
            cut.iloc[0, support] = np.nan
            rnd.iloc[0, rng.choice(avail, TOPK, replace=False)] = np.nan
            rows.append({"subject": sid, "drop_cited": (base - predict(b, cut)[0]) * sign[i],
                         "drop_random": (base - predict(b, rnd)[0]) * sign[i]})
    r = pd.DataFrame(rows)
    s = pd.DataFrame([{"subjects": r.subject.nunique(), "windows": len(r), "k": TOPK,
                       "mean_drop_cited": r.drop_cited.mean(), "mean_drop_random": r.drop_random.mean(),
                       "share_cited_gt_random": (r.drop_cited > r.drop_random).mean()}])
    s.to_csv(RES / "faithfulness.csv", index=False)
    return s


def reasoner_stats():
    p = RES / "explanations"
    recs = [json.loads(l) for f in sorted(p.glob("*.jsonl")) for l in open(f)] if p.exists() else []
    if not recs:
        return None
    r = pd.DataFrame([{"subject": x["subject"], "generator": x["generator"], "attempts": x["attempts"],
                       "verified": x["verified"], "abstain": x["output"]["abstain"],
                       "first_try_failed": x["attempts"] > 1 or not x["verified"],
                       "cited": len(x["output"].get("evidence", [])), "cited_ok": x["cited_in_top6"]} for x in recs])
    s = pd.DataFrame([{"subjects": r.subject.nunique(), "windows": len(r), "generator": ",".join(r.generator.unique()),
                       "hallucination_rate_first_try": r.first_try_failed.mean(),
                       "final_unverified_rate": (~r.verified).mean(), "abstain_rate": r.abstain.mean(),
                       "citation_accuracy": r.cited_ok.sum() / max(r.cited.sum(), 1)}])
    s.to_csv(RES / "reasoner.csv", index=False)
    return s


def reliability_plot(oof, kd):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4, 4))
    for name, d in [("n-back LOSO", oof), ("k-drive", kd)]:
        if d is None:
            continue
        bins = np.minimum((d.prob * 10).astype(int), 9)
        g = d.groupby(bins).agg(p=("prob", "mean"), y=("y", "mean"))
        ax.plot(g.p, g.y, "o-", label=f"{name} (ECE {ece(d.y.to_numpy(), d.prob.to_numpy()):.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set(xlabel="predicted P(high load)", ylabel="observed share high", title="Calibration")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(RES / "calibration.png", dpi=150)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject")
    ap.add_argument("--ablations", action="store_true")
    a = ap.parse_args()
    oof = pd.read_parquet(RES / "oof_binary.parquet")
    kd = pd.read_parquet(RES / "oof_kdrive.parquet") if (RES / "oof_kdrive.parquet").exists() else None
    if a.subject:
        sid = subject_id(a.subject)
        print(summarize(oof[oof.subject == sid], "binary", None if kd is None else kd[kd.subject == sid]).to_string())
        raise SystemExit
    tables = [summarize(oof, "binary", kd).assign(task="binary")]
    for t in ["3class", "tlx"]:
        if (RES / f"oof_{t}.parquet").exists():
            tables.append(summarize(pd.read_parquet(RES / f"oof_{t}.parquet"), t).assign(task=t))
    m = pd.concat(tables, ignore_index=True)
    m.to_csv(RES / "metrics.csv", index=False)
    print(m.to_string())
    reliability_plot(oof, kd)
    print(faithfulness().to_string())
    s = reasoner_stats()
    if s is not None:
        print(s.to_string())
    if a.ablations:
        ablations()
