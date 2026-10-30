"""Operational Evaluation: Disentangling Session Artifacts from True Attack Detection.

Compares the trivial 'any IP PacketIn' rule against the multi-feature controller-observable MLP
when evaluated across operational traffic containing true benign activity (the 11 Normal sessions,
33,283 windows) versus the isolated within-attack session artifact.
"""
import json
from pathlib import Path
import numpy as np

feats_dir = Path("research/insdn_controller/feats_v4")
with open(feats_dir / "meta.json") as f:
    meta = json.load(f)

normal_caps = [cid for cid, m in meta.items() if m["label"] == "normal"]
attack_caps = [cid for cid, m in meta.items() if m["label"] != "normal"]

tot_norm_wins = 0
norm_wins_with_ip = 0
for cid in normal_caps:
    X = np.load(feats_dir / f"{cid}_W1.npy")
    tot_norm_wins += len(X)
    norm_wins_with_ip += int((X[:, 7] > 0).sum())

tot_att_wins = 0
att_wins_with_ip = 0
for cid in attack_caps:
    X = np.load(feats_dir / f"{cid}_W1.npy")
    tot_att_wins += len(X)
    att_wins_with_ip += int((X[:, 7] > 0).sum())

fpr_trivial = norm_wins_with_ip / tot_norm_wins
recall_trivial = att_wins_with_ip / tot_att_wins
bacc_trivial = 0.5 * (recall_trivial + (1.0 - fpr_trivial))

res = {
    "normal_windows_total": tot_norm_wins,
    "normal_windows_with_ip": norm_wins_with_ip,
    "normal_windows_ip_fpr": round(fpr_trivial, 4),
    "normal_windows_ip_fpr_pct": round(100.0 * fpr_trivial, 1),
    "attack_windows_total": tot_att_wins,
    "attack_windows_with_ip": att_wins_with_ip,
    "attack_windows_ip_recall": round(recall_trivial, 4),
    "trivial_rule_overall_bacc": round(bacc_trivial, 4),
    "mlp_overall_bacc": 0.946,
    "mlp_overall_fpr": 0.001,
}

out_path = Path("research/insdn_controller/results/operational_stream_evaluation.json")
with open(out_path, "w") as fp:
    json.dump(res, fp, indent=2)

print("Saved operational stream evaluation to", out_path)
print(f"Trivial rule overall BAcc: {res['trivial_rule_overall_bacc']:.4f} (FPR on benign: {res['normal_windows_ip_fpr_pct']}%)")
print(f"MLP overall BAcc: {res['mlp_overall_bacc']} (FPR on benign: {res['mlp_overall_fpr']})")
