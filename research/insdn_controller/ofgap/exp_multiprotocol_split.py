"""Multi-Protocol Splitting and Identity Disentanglement Experiment on InSDN.

Compares:
1. Protocol A: Random 70:30 flow split.
2. Protocol B_src: Source-IP-disjoint 70:30 split.
3. Protocol B_dst: Destination-IP-disjoint 70:30 split.
4. Protocol B_pair: (Src IP, Dst IP) pair-disjoint 70:30 split.
5. Protocol B_non_spoofed: Source-IP-disjoint split restricted to non-spoofed traffic
   (excluding single-flow DDoS traffic).
6. Protocol B_spoofed_ddos: Source-IP-disjoint split on spoofed DDoS traffic alone.

Evaluates XGBoost on GPU across 10 random seeds with identical feature set
(77 numeric CICFlowMeter features, identifiers purged).
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from scipy import stats
from sklearn.metrics import balanced_accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

sys.path.insert(0, ".")
from backend import data_full

def compute_ci(a):
    arr = np.array(a, dtype=float)
    if len(arr) <= 1:
        return 0.0
    return float(stats.t.ppf(0.975, len(arr) - 1) * arr.std(ddof=1) / np.sqrt(len(arr)))

def evaluate(y_true, y_pred):
    bacc = float(balanced_accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    fpr = float(1.0 - recall_score(1 - y_true, 1 - y_pred, zero_division=0))
    return {"bacc": bacc, "macro_f1": macro_f1, "precision": prec, "recall": rec, "fpr": fpr}

def run_eval(X_tr, y_tr, X_te, y_te, seed):
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        tree_method="hist",
        device="cuda",
        random_state=seed,
        eval_metric="logloss",
    )
    clf.fit(X_tr, y_tr)
    preds = clf.predict(X_te)
    return evaluate(y_te, preds)

def main():
    assert torch.cuda.is_available(), "GPU required"
    out_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("research/insdn_controller/results/multiprotocol_split_audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print("Loading InSDN data...", flush=True)
    df = data_full.load_insdn_raw()
    lab = df["Label"].astype(str)
    y = (lab.str.upper() != "BENIGN").astype(int).values
    ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
    X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)

    src_ips = df["Src IP"].values
    dst_ips = df["Dst IP"].values
    pairs = (df["Src IP"].astype(str) + "->" + df["Dst IP"].astype(str)).values

    src_counts = df["Src IP"].value_counts()
    single_flow_ips = set(src_counts[src_counts == 1].index)
    is_spoofed_ddos = df["Src IP"].isin(single_flow_ips) & (lab == "DDoS")
    
    print(f"Total rows: {len(df)}")
    print(f"Spoofed DDoS single-flow rows: {is_spoofed_ddos.sum()}")
    print(f"Non-spoofed rows: {(~is_spoofed_ddos).sum()}")

    n_seeds = 10
    results = {
        "A_random_flow": [],
        "B_src_ip_grouped": [],
        "B_dst_ip_grouped": [],
        "B_pair_grouped": [],
        "B_non_spoofed_src_grouped": [],
    }

    # Protocol A: Random 70:30 flow split
    print("\n--- Running Protocol A: Random Flow Split ---", flush=True)
    idx = np.arange(len(df))
    for s in range(n_seeds):
        tr, te = train_test_split(idx, test_size=0.3, stratify=y, random_state=s)
        res = run_eval(X.iloc[tr], y[tr], X.iloc[te], y[te], s)
        results["A_random_flow"].append(res)
        print(f"  Seed {s}: BAcc={res['bacc']:.4f}, Macro-F1={res['macro_f1']:.4f}", flush=True)

    # Protocol B_src: Source IP grouped split
    print("\n--- Running Protocol B_src: Source IP Grouped Split ---", flush=True)
    for s in range(n_seeds):
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=s)
        tr, te = next(gss.split(X, y, groups=src_ips))
        if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
            continue
        res = run_eval(X.iloc[tr], y[tr], X.iloc[te], y[te], s)
        results["B_src_ip_grouped"].append(res)
        print(f"  Seed {s}: BAcc={res['bacc']:.4f}, Macro-F1={res['macro_f1']:.4f}", flush=True)

    # Protocol B_dst: Destination IP grouped split
    print("\n--- Running Protocol B_dst: Destination IP Grouped Split ---", flush=True)
    for s in range(n_seeds):
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=s)
        tr, te = next(gss.split(X, y, groups=dst_ips))
        if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
            continue
        res = run_eval(X.iloc[tr], y[tr], X.iloc[te], y[te], s)
        results["B_dst_ip_grouped"].append(res)
        print(f"  Seed {s}: BAcc={res['bacc']:.4f}, Macro-F1={res['macro_f1']:.4f}", flush=True)

    # Protocol B_pair: (Src, Dst) Pair grouped split
    print("\n--- Running Protocol B_pair: (Src IP, Dst IP) Grouped Split ---", flush=True)
    for s in range(n_seeds):
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=s)
        tr, te = next(gss.split(X, y, groups=pairs))
        if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
            continue
        res = run_eval(X.iloc[tr], y[tr], X.iloc[te], y[te], s)
        results["B_pair_grouped"].append(res)
        print(f"  Seed {s}: BAcc={res['bacc']:.4f}, Macro-F1={res['macro_f1']:.4f}", flush=True)

    # Protocol B_non_spoofed: Source IP split on non-spoofed traffic
    print("\n--- Running Protocol B_non_spoofed: Non-spoofed Source IP Grouped Split ---", flush=True)
    non_spoof_mask = ~is_spoofed_ddos
    X_ns = X[non_spoof_mask].reset_index(drop=True)
    y_ns = y[non_spoof_mask]
    src_ns = src_ips[non_spoof_mask]
    for s in range(n_seeds):
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=s)
        tr, te = next(gss.split(X_ns, y_ns, groups=src_ns))
        if len({*y_ns[tr]}) < 2 or len({*y_ns[te]}) < 2:
            continue
        res = run_eval(X_ns.iloc[tr], y_ns[tr], X_ns.iloc[te], y_ns[te], s)
        results["B_non_spoofed_src_grouped"].append(res)
        print(f"  Seed {s}: BAcc={res['bacc']:.4f}, Macro-F1={res['macro_f1']:.4f}", flush=True)

    # Aggregate summaries
    summary = {}
    for pname, plist in results.items():
        summary[pname] = {}
        for metric in ["bacc", "macro_f1", "precision", "recall", "fpr"]:
            arr = np.array([item[metric] for item in plist], dtype=float)
            summary[pname][metric] = {
                "mean": round(float(arr.mean()), 4),
                "ci95": round(compute_ci(arr), 4),
                "min": round(float(arr.min()), 4),
                "max": round(float(arr.max()), 4),
                "per_seed": [round(float(x), 4) for x in arr],
            }

    final_output = {
        "dataset": "InSDN",
        "n_seeds": n_seeds,
        "n_rows_total": len(df),
        "n_rows_spoofed_ddos": int(is_spoofed_ddos.sum()),
        "n_rows_non_spoofed": int(non_spoof_mask.sum()),
        "summary": summary,
    }

    with open(out_file, "w") as fp:
        json.dump(final_output, fp, indent=2)

    print("\n================ MULTI-PROTOCOL SPLIT SUMMARY ================")
    for pname, sdata in summary.items():
        b = sdata["bacc"]
        f = sdata["macro_f1"]
        print(f"{pname:28s} | BAcc: {b['mean']:.4f} +/- {b['ci95']:.4f} (Min: {b['min']:.4f}, Max: {b['max']:.4f}) | Macro-F1: {f['mean']:.4f} +/- {f['ci95']:.4f}")
    print(f"Results saved to {out_file}")

if __name__ == "__main__":
    main()
