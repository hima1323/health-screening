"""Decision metrics for the triage benchmarks (brief §5.2). Inputs are per-case levels; outputs are aggregates only.

Reference levels on ED data (ordinal): 3 = URGENT (ESI 1-2), 2 = SEE A DOCTOR (ESI 3), 1 = SELF-CARE-compatible
(ESI 4-5 and discharged home). System levels map URGENT -> 3, SEE_DOCTOR_SOON -> 2, SELF_CARE -> 1; RETAKE and an
unresolved REMEASURE are reported separately and excluded from the ordinal metrics.
"""
import numpy as np
from scipy import stats

ORD = {"URGENT": 3, "SEE_DOCTOR_SOON": 2, "SELF_CARE": 1}


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return (float("nan"),) * 3
    lo = stats.beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return k / n, lo, hi


def weighted_kappa(a, b, levels=(1, 2, 3)):
    """Linear-weighted Cohen's kappa between two ordinal ratings."""
    a, b = np.asarray(a), np.asarray(b)
    if len(a) == 0:
        return float("nan")
    idx = {v: i for i, v in enumerate(levels)}
    k = len(levels)
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[idx[x], idx[y]] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0))
    w = np.abs(np.subtract.outer(np.arange(k), np.arange(k))) / (k - 1)
    return 1 - (w * obs).sum() / (w * exp).sum() if (w * exp).sum() > 0 else float("nan")


def mcnemar(miss_a, miss_b):
    """Exact McNemar p-value on paired misses (e.g. urgent cases missed by A vs by B)."""
    a, b = np.asarray(miss_a, bool), np.asarray(miss_b, bool)
    n01, n10 = int((~a & b).sum()), int((a & ~b).sum())
    p = stats.binomtest(n01, n01 + n10).pvalue if n01 + n10 else 1.0
    return {"only_a_missed": n10, "only_b_missed": n01, "p": p}


def bootstrap_diff(hit_a, hit_b, groups=None, n_boot=1000, seed=0):
    """95% CI of mean(hit_a) - mean(hit_b), resampling cases (or `groups`, e.g. patients)."""
    a, b = np.asarray(hit_a, float), np.asarray(hit_b, float)
    rng = np.random.default_rng(seed)
    if groups is None:
        idx = [rng.integers(0, len(a), len(a)) for _ in range(n_boot)]
    else:
        g = np.asarray(groups)
        uniq, inv = np.unique(g, return_inverse=True)
        members = [np.flatnonzero(inv == i) for i in range(len(uniq))]
        idx = [np.concatenate([members[j] for j in rng.integers(0, len(uniq), len(uniq))]) for _ in range(n_boot)]
    d = [a[i].mean() - b[i].mean() for i in idx]
    return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def decision_table(levels, ref, admitted):
    """levels: system level per case; ref: reference ordinal (3/2/1, or NaN when not classifiable); admitted: bool."""
    levels, ref, admitted = np.asarray(levels, object), np.asarray(ref, float), np.asarray(admitted, bool)
    decided = np.isin(levels, list(ORD))
    sys_ord = np.array([ORD.get(l, np.nan) for l in levels], float)
    urgent, low = ref == 3, ref == 1
    referred = np.isin(levels, ["URGENT", "SEE_DOCTOR_SOON"])
    need_care = (ref >= 2) | admitted
    out = {"n": len(levels), "n_decided": int(decided.sum()),
           "retake_share": float(np.mean(levels == "RETAKE")),
           "remeasure_unresolved_share": float(np.mean(levels == "REMEASURE"))}
    k = int((levels[urgent & decided] == "URGENT").sum())
    out["urgent_sensitivity"] = clopper_pearson(k, int((urgent & decided).sum()))
    k = int((levels[low & decided] != "URGENT").sum())
    out["urgent_specificity_vs_low"] = clopper_pearson(k, int((low & decided).sum()))
    k = int(referred[need_care & decided].sum())
    out["refer_sensitivity_need_care"] = clopper_pearson(k, int((need_care & decided).sum()))
    k = int((levels[admitted & decided] == "SELF_CARE").sum())
    out["admitted_told_self_care"] = clopper_pearson(k, int((admitted & decided).sum()))
    k = int((levels[low & decided] == "SELF_CARE").sum())
    out["self_care_rate_low_acuity"] = clopper_pearson(k, int((low & decided).sum()))
    both = decided & ~np.isnan(ref)
    out["under_triage"] = float(np.mean(sys_ord[both] < ref[both])) if both.any() else float("nan")
    out["over_triage"] = float(np.mean(sys_ord[both] > ref[both])) if both.any() else float("nan")
    out["weighted_kappa"] = weighted_kappa(ref[both].astype(int), sys_ord[both].astype(int))
    cm = np.zeros((3, 3), int)
    for r, s in zip(ref[both].astype(int), sys_ord[both].astype(int)):
        cm[3 - r, 3 - s] += 1
    out["confusion_ref_rows_sys_cols_U_S_C"] = cm.tolist()
    return out
