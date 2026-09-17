"""Audit script to perform pooled post-drift evaluation (t=6..15) across all three conditions.

Computes:
- Pooled macro-F1, weighted-F1, micro-F1
- Per-class precision, recall, F1, support
- Complete confusion matrices
- Saves results to results/pooled_postdrift_evaluation.json.
"""
import json
import logging
from pathlib import Path
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from proteus.config import DEFAULT_N_JOBS
from proteus.evaluate_full import _load_day_split_data, RealDataReplaySource, N_WINDOWS, WINDOW_SIZE, DRIFT_AT_WINDOW, train_and_evaluate
from proteus.baseline_full import build_static_augmented_set
from proteus.closed_loop_full import ClosedLoopOrchestrator

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("audit_pooled_postdrift")

RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_pooled_postdrift_audit():
    log.info("Loading dataset...")
    X_stable, y_stable, X_drifted, y_drifted, class_names = _load_day_split_data()
    labels = list(range(len(class_names)))

    rng = np.random.default_rng(0)
    train_idx = rng.choice(len(X_stable), size=min(len(X_stable), 1_200_000), replace=False)
    X_train_full = X_stable[train_idx]
    y_train_full = y_stable[train_idx]

    source = RealDataReplaySource(
        X_stable, y_stable, X_drifted, y_drifted,
        n_windows=N_WINDOWS, window_size=WINDOW_SIZE, drift_at_window=DRIFT_AT_WINDOW, seed=0
    )
    windows = [(t, X, y) for t, X, y, _ in source]
    split_rng = np.random.default_rng(123)

    split_windows = [
        (t,) + ClosedLoopOrchestrator.split_eval_fit(X, y, 0.3, split_rng)
        for t, X, y in windows
    ]

    log.info("1. Training and evaluating Baseline...")
    clf_baseline, _ = train_and_evaluate(None, X_train_full, y_train_full, X_train_full[:1000], y_train_full[:1000], class_names)
    baseline_y_true_post = []
    baseline_y_pred_post = []
    for t, X_eval, y_eval, _, _ in split_windows:
        if t >= DRIFT_AT_WINDOW:
            baseline_y_true_post.extend(y_eval)
            baseline_y_pred_post.extend(clf_baseline.predict(X_eval))

    log.info("2. Training and evaluating Static Augmentation...")
    X_aug, y_aug, _ = build_static_augmented_set(X_train_full, y_train_full, class_names)
    clf_static, _ = train_and_evaluate(None, X_aug, y_aug, X_train_full[:1000], y_train_full[:1000], class_names)
    static_y_true_post = []
    static_y_pred_post = []
    for t, X_eval, y_eval, _, _ in split_windows:
        if t >= DRIFT_AT_WINDOW:
            static_y_true_post.extend(y_eval)
            static_y_pred_post.extend(clf_static.predict(X_eval))

    log.info("3. Running Closed-Loop Orchestrator...")
    orchestrator = ClosedLoopOrchestrator(
        X_train_init=X_train_full,
        y_train_init=y_train_full,
        class_names=class_names,
    )
    closed_y_true_post = []
    closed_y_pred_post = []
    for t, X_eval, y_eval, X_fit, y_fit in split_windows:
        step_result = orchestrator.step(
            t, X_eval=X_eval, y_eval=y_eval, X_fit=X_fit, y_fit=y_fit
        )
        if t >= DRIFT_AT_WINDOW:
            # Score using the adapted classifier for this window
            y_pred = orchestrator.clf.predict(X_eval)
            closed_y_true_post.extend(y_eval)
            closed_y_pred_post.extend(y_pred)

    def compute_summary(y_true, y_pred, name):
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        rep = classification_report(y_true, y_pred, labels=labels, target_names=class_names, output_dict=True, zero_division=0)
        cm = confusion_matrix(y_true, y_pred, labels=labels)

        active_classes = [c for c in class_names if rep[c]["support"] > 0]
        active_f1s = [rep[c]["f1-score"] for c in active_classes]
        active_macro_f1 = float(np.mean(active_f1s)) if active_f1s else 0.0

        per_class = {}
        for c in class_names:
            per_class[c] = {
                "precision": float(rep[c]["precision"]),
                "recall": float(rep[c]["recall"]),
                "f1": float(rep[c]["f1-score"]),
                "support": int(rep[c]["support"]),
                "pred_count": int(np.sum(y_pred == class_names.index(c)))
            }

        present_or_pred = [i for i in labels if rep[class_names[i]]["support"] > 0 or np.sum(y_pred == i) > 0]
        active_cm = cm[np.ix_(present_or_pred, present_or_pred)].tolist()
        active_cm_labels = [class_names[i] for i in present_or_pred]

        return {
            "condition": name,
            "n_pooled_rows": len(y_true),
            "n_active_classes": len(active_classes),
            "fixed_25class_ceiling": len(active_classes) / len(class_names),
            "macro_f1_25class": float(rep["macro avg"]["f1-score"]),
            "active_class_macro_f1": active_macro_f1,
            "weighted_f1": float(rep["weighted avg"]["f1-score"]),
            "micro_f1": float(f1_score(y_true, y_pred, average="micro")),
            "active_classes": active_classes,
            "per_class": per_class,
            "confusion_matrix_active": {
                "labels": active_cm_labels,
                "matrix": active_cm
            }
        }

    summary = {
        "description": "Pooled evaluation across all post-drift windows (t=6..15, total 9,000 held-out rows)",
        "baseline": compute_summary(baseline_y_true_post, baseline_y_pred_post, "Baseline"),
        "static_augmentation": compute_summary(static_y_true_post, static_y_pred_post, "Static Augmentation"),
        "closed_loop": compute_summary(closed_y_true_post, closed_y_pred_post, "Closed-Loop (BoundedBufferClassifier)")
    }

    out_file = RESULTS_DIR / "pooled_postdrift_evaluation.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Saved pooled post-drift evaluation to {out_file}")


if __name__ == "__main__":
    run_pooled_postdrift_audit()
