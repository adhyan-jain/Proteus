"""Analyze host assignments across the 10 seeds evaluated in Protocol B (GroupShuffleSplit).

Correlates test-set host presence with the exact per-seed balanced accuracy.
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

# Load InSDN data using existing loader logic
data_dir = Path("data/raw/insdn_official/extracted/InSDN_DatasetCSV")
csvs = [data_dir / "Normal_data.csv", data_dir / "OVS.csv", data_dir / "metasploitable-2.csv"]
dfs = [pd.read_csv(p, low_memory=False) for p in csvs if p.exists()]
if not dfs:
    print("InSDN CSVs not found in official path, checking data/raw...")
    sys.exit(1)

df = pd.concat(dfs, ignore_index=True)
y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values
groups = df["Src IP"].values

# Load stored scores
with open("research/insdn_controller/results/protocol_audit_insdn.json") as fp:
    audit_data = json.load(fp)
stored_scores = audit_data["B_source_ip_grouped_split"]["per_seed"]

DOMINANT_HOSTS = [
    "200.175.2.130", "192.168.20.133", "192.168.3.130", "192.168.20.134",
    "185.127.17.56", "192.168.20.2", "192.168.20.1", "74.125.168.10"
]

host_counts = df["Src IP"].value_counts().to_dict()

seeds_evaluated = []
B_scores = []
seed_idx = 0
for seed in range(40):
    if len(seeds_evaluated) == 10:
        break
    tr, te = next(GroupShuffleSplit(1, test_size=0.3, random_state=seed).split(df, y, groups=groups))
    if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
        continue
    
    test_ips = set(groups[te])
    train_ips = set(groups[tr])
    
    test_dominant = [h for h in DOMINANT_HOSTS if h in test_ips]
    train_dominant = [h for h in DOMINANT_HOSTS if h in train_ips]
    
    test_rows = len(te)
    test_frac = test_rows / len(df)
    
    score = stored_scores[len(seeds_evaluated)]
    
    seeds_evaluated.append({
        "seed": seed,
        "score_bacc": score,
        "test_frac": round(test_frac, 3),
        "primary_attacker_in_test": ("200.175.2.130" in test_ips),
        "primary_benign_in_test": ("192.168.20.133" in test_ips),
        "test_dominant_hosts": test_dominant,
        "train_dominant_hosts": train_dominant,
    })

print(f"Logged assignments for {len(seeds_evaluated)} seeds:")
for s in seeds_evaluated:
    print(f"Seed {s['seed']}: BAcc={s['score_bacc']:.3f}, test_frac={s['test_frac']:.2f}, primary_attacker_in_test={s['primary_attacker_in_test']}, primary_benign_in_test={s['primary_benign_in_test']}")

with open("research/insdn_controller/results/host_assignment_audit.json", "w") as fp:
    json.dump({"seeds": seeds_evaluated}, fp, indent=2)
print("Saved to research/insdn_controller/results/host_assignment_audit.json")
