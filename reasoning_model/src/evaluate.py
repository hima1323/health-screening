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
from train import RES, load, loso, modality

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


def trained_ref():
    return joblib.load(next((RES / "models" / "binary").glob("*.joblib")))["ref"] or "stimulus"


def ablations():
    df, feats = load()
    sets = {"all": feats, "all (ref=rest, original brief)": None,
            "contact": [c for c in feats if MODALITIES[modality(c)] == "contact"],
            "contactless (eye+AU)": [c for c in feats if MODALITIES[modality(c)] == "contactless"]}
    for m in MODALITIES:
        sets[f"only {m}"] = [c for c in feats if modality(c) == m]
        sets[f"all minus {m}"] = [c for c in feats if modality(c) != m]
    rows = []
    for name, fs in sets.items():
        if fs is None:
            d, fs = load("rest")
            oof, kd = loso(d, fs, "binary", save=False)
        else:
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


def directions():
    """Learned direction under high load per feature (sign of high-low mean z, per LOSO fold) vs literature."""
    from evidence import FEATURES
    rules = [joblib.load(p)["rules"] for p in sorted((RES / "models" / "binary").glob("*.joblib"))]
    df, feats = load(trained_ref())
    from train import task_rows
    rows_, y = task_rows(df, "binary")
    d = rows_[y == 1][feats].mean() - rows_[y == 0][feats].mean()
    out = []
    for c in feats:
        signs = [r.get(c, 0) for r in rules]
        lit = FEATURES[c[:-2]][2]
        learned = int(np.sign(sum(signs))) if abs(sum(signs)) > len(signs) / 2 else 0  # majority of folds
        out.append({"feature": c[:-2], "mean_z_high_minus_low": d[c], "folds_up": signs.count(1),
                    "folds_down": signs.count(-1), "folds_flat": signs.count(0), "learned": learned,
                    "literature": lit, "agrees": None if lit is None or learned == 0 else learned == lit})
    r = pd.DataFrame(out).sort_values("mean_z_high_minus_low", key=abs, ascending=False)
    r.to_csv(RES / "directions.csv", index=False)
    return r


def zscale():
    """How large are z-scores under each reference? (n-back test windows)"""
    rows = []
    for ref in ["rest", "stimulus"]:
        df, feats = load(ref)
        z = df[(df.study == "n-back") & (df.phase == "test")][feats].abs()
        rows.append({"ref": ref, "subjects": df.subject.nunique(), "windows": len(z),
                     "median_abs_z": float(np.nanmedian(z)), "p95_abs_z": float(np.nanpercentile(z, 95)),
                     "share_abs_z_gt_5": float((z > 5).sum().sum() / z.notna().sum().sum()),
                     "worst_feature": z.median().idxmax()[:-2], "worst_median_abs_z": z.median().max()})
    r = pd.DataFrame(rows)
    r.to_csv(RES / "zscale.csv", index=False)
    return r


def faithfulness():
    """Remove (NaN) the top-k SHAP features supporting the prediction; the model probability should move toward the
    other class more than when removing k random available features."""
    df, feats = load(trained_ref())
    oof = pd.read_parquet(RES / "oof_binary.parquet")
    rng = np.random.default_rng(0)
    rows = []
    for sid, g in oof.groupby("subject"):
        b = joblib.load(RES / "models" / "binary" / f"{sid}.joblib")
        raw = lambda Z: b["model"].predict_proba(Z)[0, 1]  # uncalibrated: isotonic steps hide small changes
        X = df.loc[df.subject == sid].set_index(["study", "phase", "level", "win_start"]) \
            .loc[list(g[["study", "phase", "level", "win_start"]].itertuples(index=False, name=None)), feats]
        X = X.reset_index(drop=True)
        sv = g[[f"shap_{c}" for c in feats]].to_numpy()
        sign = np.where(g.prob_raw.to_numpy() >= 0.5, 1, -1)
        for i in range(len(X)):
            avail = np.flatnonzero(X.iloc[i].notna().to_numpy())
            support = [j for j in np.argsort(-sv[i] * sign[i]) if j in avail and sv[i, j] * sign[i] > 0][:TOPK]
            if len(support) < TOPK:
                continue
            base = raw(X.iloc[[i]])
            cut, rnd = X.iloc[[i]].copy(), X.iloc[[i]].copy()
            cut.iloc[0, support] = np.nan
            rnd.iloc[0, rng.choice(avail, TOPK, replace=False)] = np.nan
            rows.append({"subject": sid, "drop_cited": (base - raw(cut)) * sign[i],
                         "drop_random": (base - raw(rnd)) * sign[i]})
    r = pd.DataFrame(rows)
    s = pd.DataFrame([{"subjects": r.subject.nunique(), "windows": len(r), "k": TOPK,
                       "mean_drop_cited": r.drop_cited.mean(), "mean_drop_random": r.drop_random.mean(),
                       "share_cited_gt_random": (r.drop_cited > r.drop_random).mean()}])
    s.to_csv(RES / "faithfulness.csv", index=False)
    return s


def reasoner_stats():
    """Per explanation kind (single model / fusion): first-try failures = verifier rejections (hallucination)."""
    recs = [dict(json.loads(l), record=kind) for kind, d in [("single", "explanations"), ("fusion", "explanations_fusion")]
            if (RES / d).exists() for f in sorted((RES / d).glob("*.jsonl")) for l in open(f)]
    if not recs:
        return None
    r = pd.DataFrame([{"record": x["record"], "subject": x["subject"], "generator": x["generator"],
                       "attempts": x["attempts"],
                       "verified": x["verified"], "abstain": x["output"]["abstain"],
                       "first_try_failed": bool(x["errors_first"]),
                       "cited": x["cited"], "cited_ok": x["cited_in_top6"]} for x in recs])
    s = pd.DataFrame([{"record": k, "subjects": g.subject.nunique(), "windows": len(g),
                       "generator": ",".join(g.generator.unique()),
                       "hallucination_rate_first_try": g.first_try_failed.mean(),
                       "final_unverified_rate": (~g.verified).mean(), "abstain_rate": g.abstain.mean(),
                       "citation_accuracy": g.cited_ok.sum() / max(g.cited.sum(), 1)} for k, g in r.groupby("record")])
    s.to_csv(RES / "reasoner.csv", index=False)
    return s


def fusion_faithfulness():
    """Fusion model: make the most supportive available agent unavailable; P(label) should drop more than when
    a random available agent is removed."""
    from fusion import agent_probs, fuse
    from train import task_rows
    oof = pd.read_parquet(RES / "oof_fusion.parquet")
    b0 = joblib.load(next((RES / "models" / "fusion").glob("*.joblib")))
    df, feats = load(b0["ref"] or "stimulus")
    rows_, _ = task_rows(df, "binary")
    rng, out = np.random.default_rng(0), []
    for sid, g in oof.groupby("subject"):
        b = joblib.load(RES / "models" / "fusion" / f"{sid}.joblib")
        raw, _ = agent_probs(b, rows_[rows_.subject == sid][feats])
        base, contrib = fuse(b, raw)
        sign = np.where(base >= 0.5, 1, -1)
        for i in range(len(raw)):
            av = [m for m in b["modalities"] if np.isfinite(raw.iloc[i][m])]
            sup = [m for m in av if contrib.iloc[i][m] * sign[i] > 0]
            if not sup or len(av) < 2:
                continue
            top = max(sup, key=lambda m: contrib.iloc[i][m] * sign[i])
            drop = lambda m: (base[i] - fuse(b, raw.iloc[[i]].assign(**{m: np.nan}))[0][0]) * sign[i]
            out.append({"subject": sid, "drop_top_agent": drop(top), "drop_random_agent": drop(rng.choice(av))})
    r = pd.DataFrame(out)
    s = pd.DataFrame([{"model": "fusion", "subjects": r.subject.nunique(), "windows": len(r),
                       "mean_drop_top_agent": r.drop_top_agent.mean(), "mean_drop_random_agent": r.drop_random_agent.mean(),
                       "share_top_gt_random": (r.drop_top_agent > r.drop_random_agent).mean()}])
    s.to_csv(RES / "faithfulness_fusion.csv", index=False)
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
    print(directions().round(2).to_string())
    print(zscale().round(2).to_string())
    if (RES / "oof_fusion.parquet").exists():
        print(fusion_faithfulness().round(3).to_string())
    s = reasoner_stats()
    if s is not None:
        print(s.to_string())
    if a.ablations:
        ablations()
