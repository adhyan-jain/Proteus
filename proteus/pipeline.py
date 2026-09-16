"""Orchestrates the three-condition evaluation: baseline / static-aug / closed-loop."""
import time

import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

import numpy as np
from sklearn.metrics import f1_score, classification_report

from . import baseline, data as data_mod, drift as drift_mod, fidelity, gan as gan_mod, stream


RARE_FRACTION_THRESHOLD = 0.03  # classes under this fraction of training data are "rare"
MMD_THRESHOLD = 0.25
EVAL_HOLDOUT_FRACTION = 0.3  # see _split_eval_fit


def _split_eval_fit(X, y, fraction, rng):
    """Held-out split of one stream batch, fixed before any retraining touches it: the fit
    portion is what gets absorbed into the closed-loop training set; the eval portion is never
    trained on this round and is what f1_after must be measured against. Without this split, a
    fired-drift retrain would fit the classifier on (train + X) and then score f1_after on that
    same X -- in-sample training accuracy, not a fair post-adaptation number, and not comparable
    to the baseline/static-augmentation conditions, which are always scored on batches they
    never trained on. Mirrors proteus/closed_loop_full.py's ClosedLoopOrchestrator.split_eval_fit
    (the full-scale backend) -- same bug, same fix, kept separate since the two pipelines are
    intentionally independent implementations at different scales."""
    n_eval = max(1, int(len(X) * fraction))
    perm = rng.permutation(len(X))
    eval_idx, fit_idx = perm[:n_eval], perm[n_eval:]
    return X[eval_idx], y[eval_idx], X[fit_idx], y[fit_idx]


def _identify_rare_classes(y_train, class_names):
    counts = np.bincount(y_train, minlength=len(class_names))
    frac = counts / counts.sum()
    rare = [i for i, f in enumerate(frac) if f < RARE_FRACTION_THRESHOLD and counts[i] >= 5]
    if not rare:
        rare = [int(np.argmin(counts))]
    return rare


def _per_timestep_metrics(clf, X_batch, y_batch, n_classes):
    y_pred = clf.predict(X_batch)
    labels = list(range(n_classes))
    macro_f1 = f1_score(y_batch, y_pred, labels=labels, average="macro", zero_division=0)
    per_class = f1_score(y_batch, y_pred, labels=labels, average=None, zero_division=0)
    return macro_f1, per_class.tolist()


def run_pipeline(progress_cb=None):
    """progress_cb(fraction, message) optional callback for UI progress bars."""
    def report(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    t_start = time.time()
    results = {}

    report(0.02, "Loading data...")
    d = data_mod.load_data()
    results["data_source"] = d["data_source"]
    results["class_names"] = d["class_names"]
    results["class_distribution"] = d["class_distribution"]
    results["n_features"] = d["X_train"].shape[1]

    X_train, y_train = d["X_train"], d["y_train"]
    X_test, y_test = d["X_test"], d["y_test"]
    class_names = d["class_names"]
    n_classes = len(class_names)

    report(0.08, "Training baseline classifier...")
    clf_baseline = baseline.train_classifier(X_train, y_train)
    eval_baseline = baseline.evaluate(clf_baseline, X_test, y_test, class_names)
    results["baseline_eval"] = eval_baseline

    rare_classes = _identify_rare_classes(y_train, class_names)
    results["rare_classes"] = [class_names[i] for i in rare_classes]

    report(0.15, "Training WGAN-GP on rare classes...")
    feature_mean = X_train.mean(axis=0)
    feature_std = X_train.std(axis=0)
    n_features = X_train.shape[1]

    gan = gan_mod.WGANGP(n_features, rare_classes, feature_mean, feature_std)
    gan_degraded = False
    try:
        gan.train(X_train, y_train, n_steps=300, batch_size=32)
    except Exception as e:
        gan_degraded = True
        results["gan_error"] = str(e)

    results["gan_loss_log"] = gan.loss_log
    results["gan_degraded"] = gan_degraded

    report(0.35, "Building static-augmentation condition...")
    X_aug, y_aug = X_train.copy(), y_train.copy()
    static_augmentation_errors = []
    gate = fidelity.FidelityGateLog(threshold=MMD_THRESHOLD)
    for rc in rare_classes:
        try:
            synth = gan.generate_synthetic_batch(rc, n_samples=100)
            real_recent = X_train[y_train == rc]
            admitted, score = gate.check(step=-1, synthetic_batch=synth,
                                          real_batch=real_recent, n_samples=len(synth))
            if admitted:
                X_aug = np.vstack([X_aug, synth])
                y_aug = np.concatenate([y_aug, np.full(len(synth), rc)])
        except Exception as e:
            # Generation/fidelity-check failure for one rare class must not silently vanish --
            # a failed stage is a visible failure, not a plausible-looking made-up number.
            static_augmentation_errors.append({"class": class_names[rc], "error": str(e)})
    clf_static = baseline.train_classifier(X_aug, y_aug)
    results["static_gate_log"] = gate.entries
    results["static_augmentation_errors"] = static_augmentation_errors

    report(0.45, "Building simulated traffic stream...")
    benign_idx = class_names.index("benign") if "benign" in class_names else 0
    benign_mask = y_train == benign_idx
    evasion_target_mean = (X_train[benign_mask].mean(axis=0) if benign_mask.any()
                            else X_train.mean(axis=0))
    batches = stream.build_stream(X_test, y_test, feature_std, rare_classes,
                                   evasion_target_mean=evasion_target_mean)
    results["drift_schedule"] = [b["timestep"] for b in batches if b["is_drift_injected"]]
    results["n_timesteps"] = len(batches)

    ref_confidences = baseline.confidence_distribution(clf_baseline, X_test)

    # ---- run 3 conditions over identical stream ----
    from proteus.closed_loop_full import BoundedBufferClassifier

    closed_loop_clf = BoundedBufferClassifier(
        lambda: baseline.train_classifier(X_train, y_train),
        max_ref_samples=5000, max_recent_samples=2000
    )
    closed_loop_clf.fit_initial(X_train, y_train)

    conditions = {
        "baseline": {"clf": clf_baseline, "macro_f1": [], "per_class_f1": []},
        "static_augmentation": {"clf": clf_static, "macro_f1": [], "per_class_f1": []},
        "closed_loop": {"clf": closed_loop_clf, "macro_f1": [], "per_class_f1": []},
    }

    closed_loop_gan = gan  # continues training in place (resume, not from scratch)
    closed_loop_gate = fidelity.FidelityGateLog(threshold=MMD_THRESHOLD)
    drift_events = []  # {timestep, fired, statistic, p_value}
    retrain_events = []  # {timestep, f1_before, f1_after, n_admitted}
    eval_split_rng = np.random.default_rng(123)

    n_batches = len(batches)
    for i, b in enumerate(batches):
        report(0.5 + 0.35 * (i / n_batches), f"Simulating timestep {b['timestep']}...")
        t = b["timestep"]
        X_b, y_b = b["X"], b["y"]

        for name, cond in conditions.items():
            mf1, pcf1 = _per_timestep_metrics(cond["clf"], X_b, y_b, n_classes)
            cond["macro_f1"].append(mf1)
            cond["per_class_f1"].append(pcf1)

        # drift detection driven off the closed-loop classifier's confidence
        current_conf = baseline.confidence_distribution(conditions["closed_loop"]["clf"], X_b)
        dr = drift_mod.detect_drift(current_conf, ref_confidences)
        drift_events.append({"timestep": t, **dr})

        if dr["fired"]:
            f1_before = conditions["closed_loop"]["macro_f1"][-1]
            X_eval, y_eval, X_fit, y_fit = _split_eval_fit(
                X_b, y_b, EVAL_HOLDOUT_FRACTION, eval_split_rng)

            try:
                recent_rare = [c for c in rare_classes if np.sum(y_fit == c) >= 2]
                if recent_rare:
                    closed_loop_gan.retrain(
                        X_fit[np.isin(y_fit, recent_rare)], y_fit[np.isin(y_fit, recent_rare)],
                        extra_steps=25)
                    results["gan_loss_log"] = closed_loop_gan.loss_log

                n_admitted = 0
                X_synth_list, y_synth_list = [], []
                for rc in rare_classes:
                    synth = closed_loop_gan.generate_synthetic_batch(rc, n_samples=80)
                    real_recent = X_fit if np.sum(y_fit == rc) >= 5 else X_train[y_train == rc]
                    admitted, score = closed_loop_gate.check(
                        step=t, synthetic_batch=synth, real_batch=real_recent,
                        n_samples=len(synth))
                    if admitted:
                        X_synth_list.append(synth)
                        y_synth_list.append(np.full(len(synth), rc))
                        n_admitted += len(synth)

                X_synth_combined = np.vstack(X_synth_list) if X_synth_list else None
                y_synth_combined = np.concatenate(y_synth_list) if y_synth_list else None

                closed_loop_clf.partial_fit_adaptation(X_fit, y_fit, X_synth_combined, y_synth_combined)
                mf1_after, _ = _per_timestep_metrics(
                    closed_loop_clf, X_eval, y_eval, n_classes)
                retrain_events.append({"timestep": t, "f1_before": f1_before,
                                        "f1_after": mf1_after, "n_admitted": n_admitted})
            except Exception as e:
                retrain_events.append({"timestep": t, "error": str(e)})

    results["conditions"] = {
        name: {"macro_f1": c["macro_f1"], "per_class_f1": c["per_class_f1"]}
        for name, c in conditions.items()
    }
    results["closed_loop_gate_log"] = closed_loop_gate.entries
    results["drift_events"] = drift_events
    results["retrain_events"] = retrain_events

    # final held-out report per condition for the metrics table
    final_reports = {}
    for name, cond in conditions.items():
        final_reports[name] = classification_report(
            y_test, cond["clf"].predict(X_test), target_names=class_names,
            output_dict=True, zero_division=0)
    results["final_reports"] = final_reports

    results["runtime_seconds"] = time.time() - t_start
    report(1.0, "Done.")
    return results
