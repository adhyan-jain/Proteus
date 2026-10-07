"""Metrics, paired class-stratified bootstrap and t-intervals (SPEC v1.0, sections 1.5, 2, 4).

All statistics are functions of a confusion matrix (rows = true class, columns = predicted), so
the same definition serves the point estimate (one matrix) and the bootstrap (R matrices).

Bootstrap: resampling rows with replacement *within each true class* is equivalent, for any
statistic that depends only on (true class, predictions), to drawing multinomial counts over the
occupied (true, pred_a, pred_b, ...) cells of that class. We draw the counts jointly across
models, so every model is scored on identical resampled rows (paired), and it costs
O(R * cells) instead of O(R * n).
"""
import proteus.config  # noqa: F401 -- must import before numpy/scipy to cap BLAS/OMP threads

import numpy as np
from scipy import stats as _stats


def confusion(y_true, y_pred, n_classes):
    y_true = np.asarray(y_true, dtype=np.int64)
    y_pred = np.asarray(y_pred, dtype=np.int64)
    flat = np.bincount(y_true * n_classes + y_pred, minlength=n_classes * n_classes)
    return flat.reshape(n_classes, n_classes)


def f1_from_conf(conf):
    """One-vs-rest F1 per class; 0 when a class has neither support nor predictions.
    Works on (K, K) or (R, K, K)."""
    conf = np.asarray(conf, dtype=float)
    tp = np.diagonal(conf, axis1=-2, axis2=-1)
    fn = conf.sum(axis=-1) - tp
    fp = conf.sum(axis=-2) - tp
    den = 2 * tp + fp + fn
    return np.divide(2 * tp, den, out=np.zeros_like(den), where=den > 0)


def recall_from_conf(conf):
    """Per-class recall tp / support; 0 for a class with no support. Works on (K, K) or
    (R, K, K). Used for residual eligibility (v1.1, D4)."""
    conf = np.asarray(conf, dtype=float)
    tp = np.diagonal(conf, axis1=-2, axis2=-1)
    support = conf.sum(axis=-1)
    return np.divide(tp, support, out=np.zeros_like(support), where=support > 0)


def support_from_conf(conf):
    return np.asarray(conf).sum(axis=-1)


def region_utility_conf(conf, region):
    """U(theta; D) = mean F1 over the affected-region classes."""
    region = np.asarray(sorted(region), dtype=np.int64)
    if len(region) == 0:
        raise ValueError("region_utility of an empty region is undefined")
    return f1_from_conf(conf)[..., region].mean(axis=-1)


def benign_fpr_conf(conf, benign_class):
    """Fraction of benign rows predicted as anything else; nan if there are no benign rows
    (callers must treat nan as 'safety unverifiable')."""
    conf = np.asarray(conf, dtype=float)
    n_b = conf[..., benign_class, :].sum(axis=-1)
    tp_b = conf[..., benign_class, benign_class]
    return np.divide(n_b - tp_b, n_b, out=np.full_like(n_b, np.nan), where=n_b > 0)


def stable_macro_f1_conf(conf, stable_classes):
    """Mean F1 over the supplied stable classes (the caller passes only classes with support)."""
    stable_classes = np.asarray(sorted(stable_classes), dtype=np.int64)
    if len(stable_classes) == 0:
        raise ValueError("stable_macro_f1 over no classes is undefined")
    return f1_from_conf(conf)[..., stable_classes].mean(axis=-1)


def bootstrap_confusions(y_true, preds, n_classes, n_boot, rng):
    """Jointly resampled confusion matrices for each prediction vector in `preds`.

    Returns a list (one per model) of int arrays of shape (n_boot, K, K). Every model's matrix
    in replicate r comes from the same resampled rows. Class sizes are held fixed."""
    y_true = np.asarray(y_true, dtype=np.int64)
    preds = [np.asarray(p, dtype=np.int64) for p in preds]
    for p in preds:
        if len(p) != len(y_true):
            raise ValueError("prediction/label length mismatch")
    out = [np.zeros((n_boot, n_classes, n_classes), dtype=np.int64) for _ in preds]
    for c in np.unique(y_true):
        rows = np.flatnonzero(y_true == c)
        keys = np.stack([p[rows] for p in preds], axis=1)           # (n_c, n_models)
        cells, counts = np.unique(keys, axis=0, return_counts=True)
        draws = rng.multinomial(len(rows), counts / counts.sum(), size=n_boot)  # (R, n_cells)
        for m in range(len(preds)):
            for j, pred_class in enumerate(cells[:, m]):
                out[m][:, c, pred_class] += draws[:, j]
    return out


def lcb(x, alpha):
    """alpha-quantile (lower confidence bound) of a bootstrap distribution; nan if undefined."""
    x = np.asarray(x, dtype=float)
    return float(np.nanpercentile(x, 100.0 * alpha)) if np.isfinite(x).any() else float("nan")


def ucb(x, alpha):
    """(1-alpha)-quantile (upper confidence bound) of a bootstrap distribution."""
    x = np.asarray(x, dtype=float)
    return float(np.nanpercentile(x, 100.0 * (1.0 - alpha))) if np.isfinite(x).any() \
        else float("nan")


def t_ci(values, confidence=0.95):
    """Mean and two-sided t-interval over per-seed values (n=5 -> t_4 = 2.776, not 1.96)."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    mean = float(v.mean()) if n else float("nan")
    if n < 2:
        return {"mean": mean, "lo": float("nan"), "hi": float("nan"), "n": n, "half_width":
                float("nan")}
    se = float(v.std(ddof=1)) / np.sqrt(n)
    half = float(_stats.t.ppf(0.5 + confidence / 2.0, df=n - 1)) * se
    return {"mean": mean, "lo": mean - half, "hi": mean + half, "n": n, "half_width": half}
