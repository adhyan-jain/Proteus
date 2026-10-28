"""Simulated live traffic stream, standing in for an SDN controller feed.

NOT a real network capture. Yields timestepped batches from the held-out test set,
with scheduled drift events that shift feature distributions and/or reweight class mix,
to emulate what a live controller feed showing evolving attacks might look like.
"""
import numpy as np

N_TIMESTEPS = 16
DRIFT_TIMESTEPS = (6, 11)  # 0-indexed timesteps where drift is injected
BATCH_SIZE = 60


def build_stream(X_test, y_test, feature_std, rare_class_labels, evasion_target_mean=None,
                  seed=7):
    """Returns list of (timestep, X_batch, y_batch, is_drift_step) covering N_TIMESTEPS.

    Drift is simulated as an evasion-style shift: after a drift timestep, samples of the
    rare attack classes are blended toward `evasion_target_mean` (typically the benign
    class's feature mean), mimicking attackers whose traffic starts to statistically
    resemble normal traffic to evade a classifier trained on the original attack pattern.
    A smaller blend is also applied to non-rare classes to simulate a broader shift.
    """
    rng = np.random.default_rng(seed)
    n = len(X_test)
    if evasion_target_mean is None:
        evasion_target_mean = X_test.mean(axis=0)
    noise = rng.normal(0, 1, size=X_test.shape[1]) * feature_std * 0.4

    batches = []
    active_drift = False
    for t in range(N_TIMESTEPS):
        is_drift_step = t in DRIFT_TIMESTEPS
        if is_drift_step:
            active_drift = True

        idx = rng.choice(n, size=BATCH_SIZE, replace=True)
        X_batch = X_test[idx].copy()
        y_batch = y_test[idx].copy()

        if active_drift:
            rare_mask = np.isin(y_batch, rare_class_labels)
            blend = 0.65  # how far rare-class samples move toward the evasion target
            X_batch[rare_mask] = (
                (1 - blend) * X_batch[rare_mask] + blend * evasion_target_mean + noise)
            other_mask = ~rare_mask
            blend_other = 0.15
            X_batch[other_mask] = (
                (1 - blend_other) * X_batch[other_mask]
                + blend_other * evasion_target_mean + 0.3 * noise)

        batches.append({"timestep": t, "X": X_batch, "y": y_batch,
                         "is_drift_injected": is_drift_step})
    return batches
