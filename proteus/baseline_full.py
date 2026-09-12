"""Full-scale baseline + static-augmentation classifiers (remainder of Stage 3).

Two conditions, both Random Forest on the real CICIDS2017 data from `proteus/data_full.py`:

- **Baseline**: trained on the raw, imbalanced data, no augmentation. The control condition
  everything else has to beat.
- **Static augmentation**: the literature-representative comparison condition -- the trained
  WGAN-GP (`proteus/gan_full.py`) generates a fixed batch of synthetic samples for each
  GAN-admitted class (see `gan_full.GAN_ADMIT_CLASSES` -- excludes the 3 classes flagged
  `likely_overdispersed` in the Stage 3 diagnostics, a documented decision, not a silent one),
  added once to the training set, then the classifier is trained once and frozen. This mirrors
  prior work's "augment once, train once" approach, as distinct from Proteus's own closed-loop
  drift-triggered retraining (not built in this module -- that's Stage 6).

Neither condition touches `proteus/baseline.py` or `proteus/gan.py` (the demo's small versions).
"""
import json
import logging
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.baseline_full")

RESULTS_DIR = Path(__file__).parent.parent / "results"
CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints" / "gan_full"

# Synthetic samples added per admitted class for the static-augmentation condition. A fixed,
# documented choice (not tuned/cherry-picked): large enough to meaningfully shift class balance
# for classes with only a few hundred to a couple thousand real training rows, small relative to
# the majority classes (tens/hundreds of thousands of rows) so this remains "augmentation," not
# a rebalancing to parity (which the literature this condition represents does not claim either).
SYNTHETIC_SAMPLES_PER_CLASS = 2000


def train_and_evaluate(clf, X_train, y_train, X_test, y_test, class_names, n_estimators=100):
    t0 = time.time()
    clf = RandomForestClassifier(n_estimators=n_estimators, random_state=42, n_jobs=-1) \
        if clf is None else clf
    clf.fit(X_train, y_train)
    fit_seconds = time.time() - t0

    y_pred = clf.predict(X_test)
    # present_labels handles the (expected) case where a training augmentation could shift which
    # classes appear, and guards against silently dropping any class from the report.
    labels = list(range(len(class_names)))
    report = classification_report(
        y_test, y_pred, labels=labels, target_names=class_names, output_dict=True,
        zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=labels)

    n_nan = sum(
        1 for cls in class_names
        if cls in report and any(
            (isinstance(v, float) and np.isnan(v)) for v in report[cls].values())
    )
    if n_nan:
        raise RuntimeError(
            f"{n_nan} classes produced NaN metrics -- sanity check failure, not proceeding "
            f"silently (see project ground rules on no-placeholder-metrics).")

    return clf, {
        "report": report, "confusion_matrix": cm.tolist(),
        "macro_f1": report["macro avg"]["f1-score"],
        "weighted_f1": report["weighted avg"]["f1-score"],
        "fit_seconds": fit_seconds, "n_train_rows": int(len(X_train)),
    }


def build_static_augmented_set(X_train, y_train, class_names, device="cuda"):
    from proteus.gan_full import WGANGPFull, GAN_ADMIT_CLASSES

    name_to_idx = {c: i for i, c in enumerate(class_names)}
    admit_idx = [name_to_idx[c] for c in GAN_ADMIT_CLASSES if c in name_to_idx]

    ckpt_files = sorted(CHECKPOINT_DIR.glob("epoch_*.pt"),
                         key=lambda p: int(p.stem.split("_")[1]))
    if not ckpt_files:
        raise FileNotFoundError(
            f"No WGAN-GP checkpoint found in {CHECKPOINT_DIR} -- run "
            f"proteus.gan_full.run_stage2() first (Stage 3's generator training).")
    ckpt_path = ckpt_files[-1]
    log.info(f"Loading generator checkpoint: {ckpt_path.name}")
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)

    gan = WGANGPFull(X_train.shape[1], ckpt["class_labels"], ckpt["feature_mean"],
                      ckpt["feature_std"], device=device)
    gan.G.load_state_dict(ckpt["generator"])
    gan.D.load_state_dict(ckpt["critic"])

    X_aug, y_aug = X_train.copy(), y_train.copy()
    added_counts = {}
    for c in admit_idx:
        cname = class_names[c]
        synth = gan.generate_synthetic_batch(c, n_samples=SYNTHETIC_SAMPLES_PER_CLASS)
        X_aug = np.vstack([X_aug, synth.astype(np.float32)])
        y_aug = np.concatenate([y_aug, np.full(len(synth), c, dtype=y_train.dtype)])
        added_counts[cname] = len(synth)

    del gan, ckpt
    torch.cuda.empty_cache()  # this GPU-resident generator's job is done -- free VRAM before
    # the next phase creates its own (ClosedLoopOrchestrator does, right after this returns).
    # This machine's 8GB GPU is sometimes shared with other real GPU workloads (observed: an
    # ollama LLM runner competing for VRAM caused a real CUDA OOM mid-run) -- don't hold GPU
    # memory longer than the phase that needs it.

    log.info(f"Static augmentation: added {sum(added_counts.values()):,} synthetic rows across "
             f"{len(admit_idx)} admitted classes ({SYNTHETIC_SAMPLES_PER_CLASS}/class): "
             f"{added_counts}")
    return X_aug, y_aug, added_counts


def run_stage3_classifiers():
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA not available -- this repo's absolute rule is GPU-only training (CLAUDE.md "
            "rule 1). Fix the torch install before running this.")

    from proteus.data_full import load_data_full
    log.info("Loading full CICIDS2017 data (Stage 1)...")
    d = load_data_full()
    X_train, y_train = d["X_train"], d["y_train"]
    X_test, y_test = d["X_test"], d["y_test"]
    class_names = d["class_names"]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Training baseline RF on raw imbalanced data ({len(X_train):,} rows)...")
    clf_baseline, metrics_baseline = train_and_evaluate(
        None, X_train, y_train, X_test, y_test, class_names)
    log.info(f"Baseline: macro_f1={metrics_baseline['macro_f1']:.4f} "
             f"fit={metrics_baseline['fit_seconds']:.1f}s")

    log.info("Building static-augmentation training set from the trained WGAN-GP...")
    X_aug, y_aug, added_counts = build_static_augmented_set(X_train, y_train, class_names)

    log.info(f"Training static-augmentation RF ({len(X_aug):,} rows, "
             f"{len(X_aug) - len(X_train):,} synthetic)...")
    clf_static, metrics_static = train_and_evaluate(
        None, X_aug, y_aug, X_test, y_test, class_names)
    log.info(f"Static augmentation: macro_f1={metrics_static['macro_f1']:.4f} "
             f"fit={metrics_static['fit_seconds']:.1f}s")

    delta = metrics_static["macro_f1"] - metrics_baseline["macro_f1"]
    log.info(f"\nDelta (static-aug vs baseline) macro-F1: {delta:+.4f}")

    summary = {
        "n_train_rows_baseline": int(len(X_train)),
        "n_train_rows_static_aug": int(len(X_aug)),
        "synthetic_rows_added": int(len(X_aug) - len(X_train)),
        "synthetic_samples_per_class": SYNTHETIC_SAMPLES_PER_CLASS,
        "admitted_classes": list(added_counts.keys()),
        "excluded_overdispersed_classes":
            ["Bot - Attempted", "DoS slowloris - Attempted", "FTP-Patator"],
        "baseline": {"macro_f1": metrics_baseline["macro_f1"],
                     "weighted_f1": metrics_baseline["weighted_f1"],
                     "fit_seconds": metrics_baseline["fit_seconds"],
                     "report": metrics_baseline["report"]},
        "static_augmentation": {"macro_f1": metrics_static["macro_f1"],
                                 "weighted_f1": metrics_static["weighted_f1"],
                                 "fit_seconds": metrics_static["fit_seconds"],
                                 "report": metrics_static["report"]},
        "macro_f1_delta_static_minus_baseline": delta,
    }
    with open(RESULTS_DIR / "stage3_classifiers.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"\nWrote {RESULTS_DIR / 'stage3_classifiers.json'}")
    return summary


if __name__ == "__main__":
    run_stage3_classifiers()
