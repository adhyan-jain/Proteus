"""Host-balanced training experiment on InSDN (Protocol B).
Evaluates whether sample weighting inversely proportional to host frequency mitigates
generalization collapse when dominant hosts are withheld.
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

def main():
    assert torch.cuda.is_available(), "GPU required"
    out_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("research/insdn_controller/results/host_balanced_training.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    df = data_full.load_insdn_raw()
    y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values
    ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
    X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
    src_ips = df["Src IP"].values

    b_unweighted = []
    b_weighted = []

    for seed in range(10):
        tr, te = next(GroupShuffleSplit(1, test_size=0.3, random_state=seed).split(X, y, groups=src_ips))
        if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
            continue

        # 1. Unweighted standard training
        m1 = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
        m1.fit(X.iloc[tr], y[tr])
        s1 = float(balanced_accuracy_score(y[te], m1.predict(X.iloc[te])))
        b_unweighted.append(s1)

        # 2. Host-balanced sample weighting: w_i = 1 / sqrt(N_host)
        tr_hosts = pd.Series(src_ips[tr])
        tr_counts = tr_hosts.value_counts()
        weights = tr_hosts.map(lambda h: 1.0 / (tr_counts[h] ** 0.5)).values
        weights = weights / weights.mean()

        m2 = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
        m2.fit(X.iloc[tr], y[tr], sample_weight=weights)
        s2 = float(balanced_accuracy_score(y[te], m2.predict(X.iloc[te])))
        b_weighted.append(s2)

        print(f"Seed {seed}: unweighted={s1:.4f}, host-weighted={s2:.4f}", flush=True)

    a1 = np.array(b_unweighted)
    a2 = np.array(b_weighted)

    ci1 = float(stats.t.ppf(0.975, len(a1) - 1) * a1.std(ddof=1) / np.sqrt(len(a1)))
    ci2 = float(stats.t.ppf(0.975, len(a2) - 1) * a2.std(ddof=1) / np.sqrt(len(a2)))

    results = {
        "dataset": "InSDN",
        "n_seeds": len(b_unweighted),
        "unweighted": {
            "mean": round(float(a1.mean()), 4),
            "ci95": round(ci1, 4),
            "min": round(float(a1.min()), 4),
            "max": round(float(a1.max()), 4),
            "per_seed": [round(float(x), 4) for x in a1],
        },
        "host_weighted": {
            "mean": round(float(a2.mean()), 4),
            "ci95": round(ci2, 4),
            "min": round(float(a2.min()), 4),
            "max": round(float(a2.max()), 4),
            "per_seed": [round(float(x), 4) for x in a2],
        },
        "delta_mean": round(float(a2.mean() - a1.mean()), 4),
        "worst_case_improvement": round(float(a2.min() - a1.min()), 4),
        "seed0_unweighted": round(float(a1[0]), 4),
        "seed0_weighted": round(float(a2[0]), 4),
        "seed1_unweighted": round(float(a1[1]), 4),
        "seed1_weighted": round(float(a2[1]), 4),
    }

    with open(out_file, "w") as fp:
        json.dump(results, fp, indent=2)

    print("Results saved to", out_file)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
