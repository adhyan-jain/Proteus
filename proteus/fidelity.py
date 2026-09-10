"""Fidelity gate: MMD (Gaussian-kernel) admission control for synthetic batches."""
import numpy as np


def _rbf_kernel(X, Y, gamma):
    X_sq = np.sum(X ** 2, axis=1).reshape(-1, 1)
    Y_sq = np.sum(Y ** 2, axis=1).reshape(1, -1)
    dists = X_sq + Y_sq - 2 * X @ Y.T
    dists = np.clip(dists, 0, None)
    return np.exp(-gamma * dists)


def compute_mmd(synthetic_batch, real_batch, gamma=None):
    X, Y = np.asarray(synthetic_batch, dtype=float), np.asarray(real_batch, dtype=float)
    if gamma is None:
        combined = np.vstack([X, Y])
        n = min(len(combined), 200)
        idx = np.random.default_rng(0).choice(len(combined), n, replace=False)
        sample = combined[idx]
        sq_dists = np.sum((sample[:, None, :] - sample[None, :, :]) ** 2, axis=-1)
        median_sq = np.median(sq_dists[sq_dists > 0]) if np.any(sq_dists > 0) else 1.0
        gamma = 1.0 / (median_sq + 1e-8)

    Kxx = _rbf_kernel(X, X, gamma)
    Kyy = _rbf_kernel(Y, Y, gamma)
    Kxy = _rbf_kernel(X, Y, gamma)
    mmd2 = Kxx.mean() + Kyy.mean() - 2 * Kxy.mean()
    return float(max(mmd2, 0.0))


def admit(mmd_score, threshold):
    return bool(mmd_score < threshold)


class FidelityGateLog:
    def __init__(self, threshold):
        self.threshold = threshold
        self.entries = []

    def check(self, step, synthetic_batch, real_batch, n_samples):
        score = compute_mmd(synthetic_batch, real_batch)
        admitted = admit(score, self.threshold)
        self.entries.append({"step": step, "mmd_score": score, "admitted": admitted,
                              "n_samples": n_samples})
        return admitted, score
