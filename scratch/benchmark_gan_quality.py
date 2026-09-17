"""Per-Class GAN Quality Benchmark Script.

Evaluates generated synthetic samples for all 12 GAN target classes against
real held-out validation samples across statistical, distributional, correlation,
MMD, range violation, and domain classifier distinguishability metrics.
"""
import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

from proteus.data_full import load_data_full
from proteus.gan_full import WGANGPFull, GAN_TARGET_CLASSES, mean_pairwise_distance
from proteus.fidelity import compute_mmd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("benchmark_gan_quality")

CHECKPOINT_PATH = Path("checkpoints/gan_full/epoch_80.pt")
RESULTS_DIR = Path("results")

def benchmark_class(c_idx, c_name, X_real_val, gan, n_samples=300):
    """Run full quality benchmark suite for a single target class."""
    if len(X_real_val) < 5:
        log.warning(f"Class {c_name} has insufficient real val samples ({len(X_real_val)})")
        return None

    # Generate synthetic batch
    X_synth = gan.generate_synthetic_batch(c_idx, n_samples=n_samples)

    # 1. Feature means, stds, quantiles
    mean_diff = float(np.mean(np.abs(X_real_val.mean(axis=0) - X_synth.mean(axis=0))))
    std_diff = float(np.mean(np.abs(X_real_val.std(axis=0) - X_synth.std(axis=0))))
    q25_diff = float(np.mean(np.abs(np.percentile(X_real_val, 25, axis=0) - np.percentile(X_synth, 25, axis=0))))
    q50_diff = float(np.mean(np.abs(np.percentile(X_real_val, 50, axis=0) - np.percentile(X_synth, 50, axis=0))))
    q75_diff = float(np.mean(np.abs(np.percentile(X_real_val, 75, axis=0) - np.percentile(X_synth, 75, axis=0))))

    # 2. Kolmogorov-Smirnov Test across features
    ks_stats = []
    for f in range(X_real_val.shape[1]):
        stat, _ = ks_2samp(X_real_val[:, f], X_synth[:, f])
        ks_stats.append(stat)
    mean_ks_stat = float(np.mean(ks_stats))

    # 3. Correlation matrix Frobenius distance
    with np.errstate(divide='ignore', invalid='ignore'):
        corr_real = np.corrcoef(X_real_val, rowvar=False)
        corr_synth = np.corrcoef(X_synth, rowvar=False)
        corr_real = np.nan_to_num(corr_real)
        corr_synth = np.nan_to_num(corr_synth)
    corr_frob_dist = float(np.linalg.norm(corr_real - corr_synth))

    # 4. MMD Distances (V-stat vs U-stat, raw vs standardized)
    mmd_v_raw = compute_mmd(X_synth, X_real_val, unbiased=False, standardize=False)
    mmd_v_std = compute_mmd(X_synth, X_real_val, unbiased=False, standardize=True)
    mmd_u_raw = compute_mmd(X_synth, X_real_val, unbiased=True, standardize=False)
    mmd_u_std = compute_mmd(X_synth, X_real_val, unbiased=True, standardize=True)

    # 5. Pairwise Diversity Ratio
    real_div = mean_pairwise_distance(X_real_val)
    synth_div = mean_pairwise_distance(X_synth)
    diversity_ratio = float(synth_div / real_div) if real_div > 0 else float("nan")

    # 6. Range Violation Rate
    min_real = X_real_val.min(axis=0)
    max_real = X_real_val.max(axis=0)
    violations = (X_synth < min_real) | (X_synth > max_real)
    range_violation_rate = float(violations.mean())

    # 7. Domain Classifier ROC-AUC (Real vs Synthetic)
    X_domain = np.vstack([X_real_val, X_synth])
    y_domain = np.concatenate([np.ones(len(X_real_val)), np.zeros(len(X_synth))])
    clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
    try:
        cv_scores = cross_val_score(clf, X_domain, y_domain, cv=5, scoring="roc_auc")
        domain_auc = float(np.mean(cv_scores))
    except Exception:
        domain_auc = float("nan")

    return {
        "class_name": c_name,
        "n_real_val": len(X_real_val),
        "n_synth_generated": len(X_synth),
        "mean_feature_abs_diff": mean_diff,
        "std_feature_abs_diff": std_diff,
        "q25_abs_diff": q25_diff,
        "median_abs_diff": q50_diff,
        "q75_abs_diff": q75_diff,
        "mean_ks_stat": mean_ks_stat,
        "correlation_frobenius_dist": corr_frob_dist,
        "mmd_v_raw": mmd_v_raw,
        "mmd_v_std": mmd_v_std,
        "mmd_u_raw": mmd_u_raw,
        "mmd_u_std": mmd_u_std,
        "real_diversity_dist": real_div,
        "synth_diversity_dist": synth_div,
        "diversity_ratio": diversity_ratio,
        "range_violation_rate": range_violation_rate,
        "domain_classifier_auc": domain_auc,
    }

def main():
    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"Checkpoint {CHECKPOINT_PATH} not found!")

    log.info("Loading full CICIDS2017 dataset...")
    d = load_data_full()
    X_val, y_val = d["X_val"], d["y_val"]
    class_names = d["class_names"]
    name_to_idx = {c: i for i, c in enumerate(class_names)}

    log.info(f"Loading GAN checkpoint from {CHECKPOINT_PATH}...")
    gan = WGANGPFull.load_from_checkpoint(CHECKPOINT_PATH)

    results = {}
    csv_rows = []

    log.info("\nStarting per-class GAN quality benchmark across 12 target classes...")
    for c_name in GAN_TARGET_CLASSES:
        if c_name not in name_to_idx:
            continue
        c_idx = name_to_idx[c_name]
        X_real_val = X_val[y_val == c_idx]
        metrics = benchmark_class(c_idx, c_name, X_real_val, gan)
        if metrics:
            results[c_name] = metrics
            csv_rows.append(metrics)
            log.info(f"[{c_name:<36}] KS={metrics['mean_ks_stat']:.3f} | MMD_U_Std={metrics['mmd_u_std']:.4f} | "
                     f"DivRatio={metrics['diversity_ratio']:.3f} | DomainAUC={metrics['domain_classifier_auc']:.3f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "gan_quality_by_class.json"
    csv_path = RESULTS_DIR / "gan_quality_by_class.csv"

    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    df_csv = pd.DataFrame(csv_rows)
    df_csv.to_csv(csv_path, index=False)
    log.info(f"\nSaved benchmark outputs to {json_path} and {csv_path}")

if __name__ == "__main__":
    main()
