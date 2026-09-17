"""Demo Pipeline Drift Severity & Window-Size Sensitivity Matrix Script.

Evaluates the demo streaming pipeline across a grid of drift severities
(0%, 15%, 30%, 45%, 65%) and stream window sizes (60, 120, 300, 600).
Outputs per-timestep metrics and drift/fidelity events to results/demo_sensitivity_matrix.json.
"""
import json
import logging
from pathlib import Path
import numpy as np

from proteus.data import load_data
from proteus.baseline import train_classifier, confidence_distribution, evaluate
from proteus.drift import detect_drift
from proteus.fidelity import FidelityGateLog
from proteus.gan import WGANGP
from proteus.closed_loop_full import BoundedBufferClassifier
from sklearn.metrics import f1_score

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("test_demo_sensitivity")

RESULTS_DIR = Path("results")
N_TIMESTEPS = 16
DRIFT_TIMESTEPS = (6, 11)

def build_custom_stream(X_test, y_test, feature_std, rare_class_labels, evasion_target_mean, blend_severity, batch_size, seed=7):
    rng = np.random.default_rng(seed)
    n = len(X_test)
    noise = rng.normal(0, 1, size=X_test.shape[1]) * feature_std * 0.4

    batches = []
    active_drift = False
    for t in range(N_TIMESTEPS):
        is_drift_step = t in DRIFT_TIMESTEPS
        if is_drift_step:
            active_drift = True

        idx = rng.choice(n, size=batch_size, replace=True)
        X_batch = X_test[idx].copy()
        y_batch = y_test[idx].copy()

        if active_drift and blend_severity > 0.0:
            rare_mask = np.isin(y_batch, rare_class_labels)
            blend = blend_severity
            X_batch[rare_mask] = (
                (1 - blend) * X_batch[rare_mask] + blend * evasion_target_mean + noise)
            other_mask = ~rare_mask
            blend_other = blend_severity * 0.25
            X_batch[other_mask] = (
                (1 - blend_other) * X_batch[other_mask] + blend_other * evasion_target_mean + 0.3 * noise)

        batches.append({"timestep": t, "X": X_batch, "y": y_batch, "is_drift_injected": is_drift_step})
    return batches

def evaluate_grid_point(d, blend_severity, batch_size):
    X_train, y_train = d["X_train"], d["y_train"]
    X_test, y_test = d["X_test"], d["y_test"]
    class_names = d["class_names"]
    n_classes = len(class_names)
    
    # Identify rare classes
    counts = np.bincount(y_train, minlength=n_classes)
    frac = counts / counts.sum()
    rare_classes = [i for i, f in enumerate(frac) if f < 0.03 and counts[i] >= 5]
    if not rare_classes:
        rare_classes = [int(np.argmin(counts))]

    clf_base = train_classifier(X_train, y_train)
    ref_conf = confidence_distribution(clf_base, X_test)

    # Train GAN
    feature_mean = X_train.mean(axis=0)
    feature_std = X_train.std(axis=0)
    gan = WGANGP(X_train.shape[1], rare_classes, feature_mean, feature_std)
    gan.train(X_train, y_train, n_steps=300, batch_size=32)

    benign_idx = class_names.index("benign") if "benign" in class_names else 0
    benign_mask = y_train == benign_idx
    evasion_target = X_train[benign_mask].mean(axis=0) if benign_mask.any() else X_train.mean(axis=0)

    batches = build_custom_stream(X_test, y_test, feature_std, rare_classes, evasion_target, blend_severity, batch_size)

    closed_loop_clf = BoundedBufferClassifier(lambda: train_classifier(X_train, y_train), max_ref_samples=5000, max_recent_samples=2000)
    closed_loop_clf.fit_initial(X_train, y_train)

    drift_fired_count = 0
    admitted_count = 0
    f1_series = []

    eval_rng = np.random.default_rng(123)
    gate = FidelityGateLog(threshold=0.25)

    for b in batches:
        X_b, y_b = b["X"], b["y"]
        perm = eval_rng.permutation(len(X_b))
        n_eval = max(1, int(len(X_b) * 0.3))
        X_eval, y_eval = X_b[perm[:n_eval]], y_b[perm[:n_eval]]
        X_fit, y_fit = X_b[perm[n_eval:]], y_b[perm[n_eval:]]

        # Drift check
        conf = confidence_distribution(clf_base, X_b)
        dr = detect_drift(conf, ref_conf)
        if dr["fired"]:
            drift_fired_count += 1
            recent_rare = [c for c in rare_classes if np.sum(y_fit == c) >= 2]
            if recent_rare:
                try:
                    gan.retrain(X_fit[np.isin(y_fit, recent_rare)], y_fit[np.isin(y_fit, recent_rare)], extra_steps=25)
                except Exception:
                    pass

            X_synth_list, y_synth_list = [], []
            for rc in rare_classes:
                synth = gan.generate_synthetic_batch(rc, n_samples=80)
                real_recent = X_fit[y_fit == rc] if np.sum(y_fit == rc) >= 5 else X_train[y_train == rc]
                admitted, score = gate.check(b["timestep"], synth, real_recent, len(synth))
                if admitted:
                    admitted_count += len(synth)
                    X_synth_list.append(synth)
                    y_synth_list.append(np.full(len(synth), rc))

            X_s = np.vstack(X_synth_list) if X_synth_list else None
            y_s = np.concatenate(y_synth_list) if y_synth_list else None
            closed_loop_clf.partial_fit_adaptation(X_fit, y_fit, X_s, y_s)

        preds = closed_loop_clf.predict(X_eval)
        f1 = f1_score(y_eval, preds, labels=list(range(n_classes)), average="macro", zero_division=0)
        f1_series.append(float(f1))

    return {
        "drift_severity": blend_severity,
        "batch_size": batch_size,
        "drift_fired_count": drift_fired_count,
        "synthetic_samples_admitted": admitted_count,
        "initial_macro_f1": f1_series[0],
        "final_macro_f1": f1_series[-1],
        "mean_post_drift_f1": float(np.mean(f1_series[6:])),
    }

def main():
    log.info("Loading demo data...")
    d = load_data()
    
    severities = [0.0, 0.15, 0.30, 0.45, 0.65]
    batch_sizes = [60, 120, 300, 600]

    matrix_results = []
    print(f"\n{'Severity':<10} | {'BatchSize':<10} | {'DriftsFired':<12} | {'Admitted':<10} | {'PostDriftF1':<12}")
    print("-" * 65)

    for sev in severities:
        for bs in batch_sizes:
            res = evaluate_grid_point(d, sev, bs)
            matrix_results.append(res)
            print(f"{sev:<10.2f} | {bs:<10d} | {res['drift_fired_count']:<12d} | {res['synthetic_samples_admitted']:<10d} | {res['mean_post_drift_f1']:<12.4f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "demo_sensitivity_matrix.json"
    with open(out_path, "w") as f:
        json.dump(matrix_results, f, indent=2)
    log.info(f"\nSaved demo sensitivity matrix to {out_path}")

if __name__ == "__main__":
    main()
