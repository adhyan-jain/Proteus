"""Downstream Classifier Augmentation Utility Study.

Compares classifier evaluation performance on held-out real test data under five conditions:
- Condition A: Real training data only
- Condition B: Real + Gaussian noise augmentation
- Condition C: Real + Ungated GAN synthetic samples
- Condition D: Real + MMD-gated GAN synthetic samples
- Condition E: Real + Shuffled/random synthetic control
"""
import json
import logging
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

from proteus.data_full import load_data_full
from proteus.gan_full import WGANGPFull, GAN_TARGET_CLASSES
from proteus.fidelity import compute_mmd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("test_gan_utility")

CHECKPOINT_PATH = Path("checkpoints/gan_full/epoch_80.pt")
RESULTS_DIR = Path("results")

def train_and_eval(X_tr, y_tr, X_te, y_te, labels):
    clf = RandomForestClassifier(n_estimators=100, max_depth=20, random_state=42, n_jobs=-1)
    clf.fit(X_tr, y_tr)
    preds = clf.predict(X_te)
    report = classification_report(y_te, preds, labels=labels, output_dict=True, zero_division=0)
    return report

def run_utility_study():
    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"Checkpoint {CHECKPOINT_PATH} not found!")

    log.info("Loading full CICIDS2017 dataset...")
    d = load_data_full()
    X_train, y_train = d["X_train"], d["y_train"]
    X_test, y_test = d["X_test"], d["y_test"]
    class_names = d["class_names"]
    name_to_idx = {c: i for i, c in enumerate(class_names)}
    target_idx = [name_to_idx[c] for c in GAN_TARGET_CLASSES if c in name_to_idx]

    log.info(f"Loading GAN checkpoint from {CHECKPOINT_PATH}...")
    gan = WGANGPFull.load_from_checkpoint(CHECKPOINT_PATH)

    # Generate synthetic batches per class
    synth_dict = {}
    gated_synth_dict = {}
    noise_dict = {}
    shuffled_dict = {}

    log.info("Generating synthetic samples & performing fidelity gating...")
    for c_name in GAN_TARGET_CLASSES:
        if c_name not in name_to_idx:
            continue
        c = name_to_idx[c_name]
        real_c = X_train[y_train == c]
        if len(real_c) < 5:
            continue
        
        synth = gan.generate_synthetic_batch(c, n_samples=min(2000, len(real_c)))
        synth_dict[c] = synth

        # MMD Gating check (standardized MMD, threshold 0.25)
        score = compute_mmd(synth, real_c, standardize=True)
        if score < 0.25:
            gated_synth_dict[c] = synth

        # Gaussian Noise matching real mean and std
        std = np.std(real_c, axis=0) + 1e-8
        noise = real_c + np.random.normal(0, 0.1 * std, size=real_c.shape)
        noise_dict[c] = noise

        # Shuffled feature control
        shuffled = synth.copy()
        for f in range(shuffled.shape[1]):
            np.random.shuffle(shuffled[:, f])
        shuffled_dict[c] = shuffled

    log.info("Evaluating Condition A: Real Train Data Only...")
    rep_a = train_and_eval(X_train, y_train, X_test, y_test, target_idx)

    log.info("Evaluating Condition B: Real + Gaussian Noise...")
    X_b = np.vstack([X_train] + list(noise_dict.values()))
    y_b = np.concatenate([y_train] + [np.full(len(arr), c) for c, arr in noise_dict.items()])
    rep_b = train_and_eval(X_b, y_b, X_test, y_test, target_idx)

    log.info("Evaluating Condition C: Real + Ungated GAN Synthetic...")
    X_c = np.vstack([X_train] + list(synth_dict.values()))
    y_c = np.concatenate([y_train] + [np.full(len(arr), c) for c, arr in synth_dict.items()])
    rep_c = train_and_eval(X_c, y_c, X_test, y_test, target_idx)

    log.info("Evaluating Condition D: Real + MMD-Gated GAN Synthetic...")
    if gated_synth_dict:
        X_d = np.vstack([X_train] + list(gated_synth_dict.values()))
        y_d = np.concatenate([y_train] + [np.full(len(arr), c) for c, arr in gated_synth_dict.items()])
    else:
        X_d, y_d = X_train, y_train
    rep_d = train_and_eval(X_d, y_d, X_test, y_test, target_idx)

    log.info("Evaluating Condition E: Real + Shuffled/Random Control...")
    X_e = np.vstack([X_train] + list(shuffled_dict.values()))
    y_e = np.concatenate([y_train] + [np.full(len(arr), c) for c, arr in shuffled_dict.items()])
    rep_e = train_and_eval(X_e, y_e, X_test, y_test, target_idx)

    summary = {
        "condition_a_real_only": {
            "macro_f1": rep_a["macro avg"]["f1-score"],
            "weighted_f1": rep_a["weighted avg"]["f1-score"],
        },
        "condition_b_real_plus_noise": {
            "macro_f1": rep_b["macro avg"]["f1-score"],
            "weighted_f1": rep_b["weighted avg"]["f1-score"],
        },
        "condition_c_real_plus_ungated_gan": {
            "macro_f1": rep_c["macro avg"]["f1-score"],
            "weighted_f1": rep_c["weighted avg"]["f1-score"],
        },
        "condition_d_real_plus_gated_gan": {
            "macro_f1": rep_d["macro avg"]["f1-score"],
            "weighted_f1": rep_d["weighted avg"]["f1-score"],
        },
        "condition_e_real_plus_shuffled": {
            "macro_f1": rep_e["macro avg"]["f1-score"],
            "weighted_f1": rep_e["weighted avg"]["f1-score"],
        },
    }

    print("\n" + "=" * 65)
    print("DOWNSTREAM AUGMENTATION UTILITY STUDY RESULTS (Target Classes)")
    print("=" * 65)
    for cond_name, metrics in summary.items():
        print(f"{cond_name:<36} | Macro-F1: {metrics['macro_f1']:.4f} | Weighted-F1: {metrics['weighted_f1']:.4f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "gan_downstream_utility.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"\nSaved downstream utility results to {out_path}")

if __name__ == "__main__":
    run_utility_study()
