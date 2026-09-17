"""MMD Estimator Audit & Empirical Sanity Matrix Diagnostic Script.

Evaluates MMD distance under V-statistic (biased) vs U-statistic (unbiased),
for both raw features and standardized features across test cases A-G.
"""
import json
import os
import numpy as np
import pandas as pd
from pathlib import Path
from proteus.fidelity import compute_mmd

RESULTS_DIR = Path("results")

def generate_cases():
    """Generate synthetic/toy and real data slices for MMD test cases A-G."""
    rng = np.random.default_rng(42)
    n_samples = 300
    n_features = 20

    # Real Class A: Multi-variate Normal
    mean_a = rng.uniform(0, 10, size=n_features)
    cov_a = np.diag(rng.uniform(1, 5, size=n_features))
    real_a1 = rng.multivariate_normal(mean_a, cov_a, size=n_samples)
    real_a2 = rng.multivariate_normal(mean_a, cov_a, size=n_samples)
    
    # Bootstrapped A
    bootstrap_idx = rng.choice(n_samples, size=n_samples, replace=True)
    real_a_boot = real_a1[bootstrap_idx]

    # Real Class B: Different mean & covariance
    mean_b = mean_a + rng.uniform(5, 15, size=n_features)
    cov_b = np.diag(rng.uniform(2, 8, size=n_features))
    real_b = rng.multivariate_normal(mean_b, cov_b, size=n_samples)

    # Gaussian Noise with matching mean and std of A
    std_a = np.std(real_a1, axis=0)
    gaussian_noise = rng.normal(loc=mean_a, scale=std_a, size=(n_samples, n_features))

    # Shifted A (15% and 30% mean shift)
    shifted_a_15 = real_a1 + 0.15 * std_a
    shifted_a_30 = real_a1 + 0.30 * std_a

    # Synthetic A (WGAN-like: matching mean, slightly lower variance)
    synth_a = rng.multivariate_normal(mean_a, cov_a * 0.8, size=n_samples)

    cases = {
        "Case A (Real A vs Held-out Real A)": (real_a1, real_a2),
        "Case B (Real A vs Self Real A)": (real_a1, real_a1),
        "Case C (Real A vs Bootstrapped Real A)": (real_a1, real_a_boot),
        "Case D (Real A vs Real Class B)": (real_a1, real_b),
        "Case E (Real A vs Synthetic Class A)": (real_a1, synth_a),
        "Case F (Real A vs Gaussian Noise)": (real_a1, gaussian_noise),
        "Case G1 (Real A vs 15% Shifted A)": (real_a1, shifted_a_15),
        "Case G2 (Real A vs 30% Shifted A)": (real_a1, shifted_a_30),
    }
    return cases

def run_matrix():
    cases = generate_cases()
    results = {}

    print(f"\n{'Test Case':<42} | {'V-Raw':<10} | {'V-Std':<10} | {'U-Raw':<10} | {'U-Std':<10}")
    print("-" * 92)

    for case_name, (X, Y) in cases.items():
        v_raw = compute_mmd(X, Y, gamma=None, unbiased=False, standardize=False)
        v_std = compute_mmd(X, Y, gamma=None, unbiased=False, standardize=True)
        u_raw = compute_mmd(X, Y, gamma=None, unbiased=True, standardize=False)
        u_std = compute_mmd(X, Y, gamma=None, unbiased=True, standardize=True)

        results[case_name] = {
            "v_statistic_raw": round(v_raw, 6),
            "v_statistic_standardized": round(v_std, 6),
            "u_statistic_raw": round(u_raw, 6),
            "u_statistic_standardized": round(u_std, 6),
        }

        print(f"{case_name:<42} | {v_raw:<10.6f} | {v_std:<10.6f} | {u_raw:<10.6f} | {u_std:<10.6f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "mmd_sanity_matrix.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved MMD sanity matrix to {out_path}")

if __name__ == "__main__":
    run_matrix()
