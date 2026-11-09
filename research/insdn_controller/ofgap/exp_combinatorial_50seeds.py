"""Combinatorial & Seed Expansion Audit across 50 Seeds on InSDN Protocol B.

Evaluates:
1. Exact allocation of all 8 dominant hosts across 50 random seeds of GroupShuffleSplit(0.3).
2. Correlation between test partition row share and Balanced Accuracy.
3. Empirical frequency of dominant host retention/exclusion vs. exact Hypergeometric expectation.
4. Distribution of Balanced Accuracy across 50 seeds to evaluate stability and bimodality.
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from scipy import stats
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, ".")
from backend import data_full

DOMINANT_HOSTS = [
    "200.175.2.130",   # Primary attacker (110,799 flows)
    "192.168.20.133",  # Primary benign host (53,790 flows)
    "192.168.3.130",   # Attacker/Internal (37,374 flows)
    "192.168.20.134",  # DoS attacker (5,116 flows)
    "185.127.17.56",   # Benign (3,917 flows)
    "192.168.20.2",    # Benign (3,223 flows)
    "192.168.20.1",    # Benign (680 flows)
    "74.125.168.10"    # Benign (505 flows)
]

def main():
    assert torch.cuda.is_available(), "GPU required"
    out_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("research/insdn_controller/results/combinatorial_audit_50seeds.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print("Loading InSDN data...", flush=True)
    df = data_full.load_insdn_raw()
    y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values
    ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
    X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
    src_ips = df["Src IP"].values

    unique_groups = np.unique(src_ips)
    M = len(unique_groups)
    # scikit-learn's _validate_shuffle_split sets n_test = ceil(test_size * n_samples)
    k = int(np.ceil(0.3 * M))

    # Exact Hypergeometric Probabilities
    p_both_retained_hyper = ((M - k) / M) * ((M - k - 1) / (M - 1))
    p_both_test_hyper = (k / M) * ((k - 1) / (M - 1))
    p_att_test_hyper = (k / M) * ((M - k) / (M - 1))
    p_ben_test_hyper = ((M - k) / M) * (k / (M - 1))

    print(f"Total groups M={M}, test groups k={k} (scikit-learn ceil rule: ceil(0.3*{M})={k})")
    print(f"Hypergeometric Theory: P(neither dominant withheld) = {p_both_retained_hyper:.6f} ({p_both_retained_hyper*100:.2f}%)")

    n_eval_seeds = 50
    seeds_data = []

    print(f"\nEvaluating {n_eval_seeds} seeds on Protocol B...", flush=True)

    for seed in range(n_eval_seeds):
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed)
        tr, te = next(gss.split(X, y, groups=src_ips))
        if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
            continue

        test_ips = set(src_ips[te])
        att_in_test = "200.175.2.130" in test_ips
        ben_in_test = "192.168.20.133" in test_ips
        test_dominant = [h for h in DOMINANT_HOSTS if h in test_ips]

        clf = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            tree_method="hist",
            device="cuda",
            random_state=seed,
            eval_metric="logloss",
        )
        clf.fit(X.iloc[tr], y[tr])
        preds = clf.predict(X.iloc[te])
        bacc = float(balanced_accuracy_score(y[te], preds))

        test_frac = float(len(te) / len(df))

        seeds_data.append({
            "seed": seed,
            "bacc": round(bacc, 4),
            "test_frac": round(test_frac, 4),
            "primary_attacker_in_test": att_in_test,
            "primary_benign_in_test": ben_in_test,
            "dominant_hosts_in_test": test_dominant,
            "num_dominant_hosts_in_test": len(test_dominant),
        })

        if seed % 5 == 0 or seed < 5:
            print(f"Seed {seed:2d}: BAcc={bacc:.4f}, test_frac={test_frac:.3f}, att_in_test={att_in_test}, ben_in_test={ben_in_test}, dominant={len(test_dominant)}", flush=True)

    baccs = np.array([s["bacc"] for s in seeds_data])
    test_fracs = np.array([s["test_frac"] for s in seeds_data])

    corr, pval = stats.pearsonr(test_fracs, baccs)
    spearman_corr, spearman_pval = stats.spearmanr(test_fracs, baccs)

    n_neither = sum(not s["primary_attacker_in_test"] and not s["primary_benign_in_test"] for s in seeds_data)
    n_both = sum(s["primary_attacker_in_test"] and s["primary_benign_in_test"] for s in seeds_data)
    n_att_only = sum(s["primary_attacker_in_test"] and not s["primary_benign_in_test"] for s in seeds_data)
    n_ben_only = sum(not s["primary_attacker_in_test"] and s["primary_benign_in_test"] for s in seeds_data)
    total_seeds = len(seeds_data)

    empirical_freqs = {
        "neither_withheld": round(n_neither / total_seeds, 4),
        "both_withheld": round(n_both / total_seeds, 4),
        "att_only_withheld": round(n_att_only / total_seeds, 4),
        "ben_only_withheld": round(n_ben_only / total_seeds, 4),
    }

    hyper_theory = {
        "M_groups": M,
        "k_test_groups": k,
        "neither_withheld": round(p_both_retained_hyper, 4),
        "both_withheld": round(p_both_test_hyper, 4),
        "att_only_withheld": round(p_att_test_hyper, 4),
        "ben_only_withheld": round(p_ben_test_hyper, 4),
        "exact_prob_neither_retained": float(p_both_retained_hyper),
        "exact_prob_att_only_withheld": float(p_att_test_hyper),
        "exact_prob_ben_only_withheld": float(p_ben_test_hyper),
        "exact_prob_both_withheld": float(p_both_test_hyper),
    }

    bacc_by_regime = {
        "neither_withheld": [s["bacc"] for s in seeds_data if not s["primary_attacker_in_test"] and not s["primary_benign_in_test"]],
        "att_only_withheld": [s["bacc"] for s in seeds_data if s["primary_attacker_in_test"] and not s["primary_benign_in_test"]],
        "ben_only_withheld": [s["bacc"] for s in seeds_data if not s["primary_attacker_in_test"] and s["primary_benign_in_test"]],
        "both_withheld": [s["bacc"] for s in seeds_data if s["primary_attacker_in_test"] and s["primary_benign_in_test"]],
    }

    regime_summary = {}
    for rname, rvals in bacc_by_regime.items():
        if rvals:
            arr = np.array(rvals)
            regime_summary[rname] = {
                "count": len(arr),
                "mean": round(float(arr.mean()), 4),
                "std": round(float(arr.std()), 4),
                "min": round(float(arr.min()), 4),
                "max": round(float(arr.max()), 4),
            }

    ci95 = float(stats.t.ppf(0.975, total_seeds - 1) * baccs.std(ddof=1) / np.sqrt(total_seeds))

    summary = {
        "dataset": "InSDN",
        "total_seeds_evaluated": total_seeds,
        "overall_bacc": {
            "mean": round(float(baccs.mean()), 4),
            "std": round(float(baccs.std()), 4),
            "ci95": round(ci95, 4),
            "min": round(float(baccs.min()), 4),
            "max": round(float(baccs.max()), 4),
            "median": round(float(np.median(baccs)), 4),
            "iqr": round(float(np.percentile(baccs, 75) - np.percentile(baccs, 25)), 4),
        },
        "test_frac_vs_bacc_correlation": {
            "pearson_r": round(corr, 4),
            "pearson_p": float(pval),
            "spearman_rho": round(spearman_corr, 4),
            "spearman_p": float(spearman_pval),
        },
        "hypergeometric_theory": hyper_theory,
        "empirical_frequencies_50seeds": empirical_freqs,
        "regime_summary": regime_summary,
        "seeds": seeds_data,
    }

    with open(out_file, "w") as fp:
        json.dump(summary, fp, indent=2)

    print("\n================ 50-SEED AUDIT SUMMARY ================")
    print(f"Overall BAcc (50 seeds): {summary['overall_bacc']['mean']:.4f} +/- {summary['overall_bacc']['ci95']:.4f} [Min: {summary['overall_bacc']['min']:.4f}, Max: {summary['overall_bacc']['max']:.4f}]")
    print(f"Correlation between test row fraction and BAcc: r={corr:.4f} (p={pval:.2e})")
    print(f"Regime breakdown:")
    for rname, rstat in regime_summary.items():
        print(f"  {rname:20s} (N={rstat['count']:2d}): Mean={rstat['mean']:.4f}, Range=[{rstat['min']:.4f}, {rstat['max']:.4f}]")
    print(f"Results saved to {out_file}")

if __name__ == "__main__":
    main()
