"""Operational Stream Evaluation: Evaluating Shortcut Rules and MLP across Benign and Attack Streams.

Evaluates the trivial 'any IP PacketIn' baseline against the multi-feature controller MLP
across both the strict labeled window set (38,050 windows) and the raw unmasked stream
(42,099 windows), reading model metrics directly from v4_strict_W1.json.
"""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import exp_ctrl2

out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("research/insdn_controller/results/operational_stream_evaluation.json")
feats_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("research/insdn_controller/feats_v4")
v4_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "results" / "v4_strict_W1.json"

# 1. Strict window set evaluation (exact same set evaluated by MLP)
caps = exp_ctrl2.load(feats_dir, 1.0, "strict")
X, y, inatt, cap_idx, nonempty = exp_ctrl2.stack(caps, extra=True)

ip_col = exp_ctrl2.FEATS.index("pin_src_ip")
p_triv = X[:, ip_col] > 0

rec_strict = float((p_triv & (y == 1)).sum() / (y == 1).sum())
fpr_strict = float((p_triv & (y == 0)).sum() / (y == 0).sum())
bacc_strict = 0.5 * (rec_strict + (1.0 - fpr_strict))

tot_norm = int((inatt == 0).sum())
norm_with_ip = int((p_triv[inatt == 0]).sum())
fpr_normal = norm_with_ip / tot_norm

# 2. Raw unmasked stream (42,099 windows, including ambiguous attack-session windows)
meta = json.loads((feats_dir / "meta.json").read_text())
raw_norm = sum(len(np.load(feats_dir / f"{cid}_W1.npy")) for cid, m in meta.items() if m["label"] == "normal")
raw_norm_ip = sum((np.load(feats_dir / f"{cid}_W1.npy")[:, 7] > 0).sum() for cid, m in meta.items() if m["label"] == "normal")
raw_att = sum(len(np.load(feats_dir / f"{cid}_W1.npy")) for cid, m in meta.items() if m["label"] != "normal")
raw_att_ip = sum((np.load(feats_dir / f"{cid}_W1.npy")[:, 7] > 0).sum() for cid, m in meta.items() if m["label"] != "normal")
raw_fpr = raw_norm_ip / raw_norm
raw_rec = raw_att_ip / raw_att
raw_bacc = 0.5 * (raw_rec + (1.0 - raw_fpr))

# 3. Dynamic MLP results from v4_strict_W1.json
with open(v4_path) as f:
    v4 = json.load(f)

mlp_bacc = v4["A_grouped_cv"]["mlp_all"]["bacc"]["mean"]
mlp_fpr = v4["A_grouped_cv"]["mlp_all"]["fpr"]["mean"]
mlp_norm_fpr = v4["A_grouped_cv"]["mlp_all_normal_captures_fpr"]["mean"]

res = {
    "strict_windows_total": len(y),
    "strict_attack_windows": int((y == 1).sum()),
    "strict_benign_windows": int((y == 0).sum()),
    "strict_trivial_rule_recall": round(rec_strict, 4),
    "strict_trivial_rule_fpr": round(fpr_strict, 4),
    "strict_trivial_rule_bacc": round(bacc_strict, 4),
    "normal_windows_total": tot_norm,
    "normal_windows_with_ip": norm_with_ip,
    "normal_windows_ip_fpr": round(fpr_normal, 4),
    "normal_windows_ip_fpr_pct": round(100.0 * fpr_normal, 1),
    "raw_stream_windows_total": raw_norm + raw_att,
    "raw_stream_trivial_bacc": round(raw_bacc, 4),
    "mlp_overall_bacc": round(mlp_bacc, 4),
    "mlp_overall_fpr": round(mlp_fpr, 4),
    "mlp_normal_fpr": round(mlp_norm_fpr, 4),
}

out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as fp:
    json.dump(res, fp, indent=2)

print("Saved operational stream evaluation to", out_path)
print(f"Strict set trivial rule: Recall={res['strict_trivial_rule_recall']}, FPR={res['strict_trivial_rule_fpr']}, BAcc={res['strict_trivial_rule_bacc']}")
print(f"Normal traffic trivial rule FPR: {res['normal_windows_ip_fpr_pct']}% ({res['normal_windows_with_ip']}/{res['normal_windows_total']})")
print(f"Raw stream trivial rule BAcc: {res['raw_stream_trivial_bacc']}")
print(f"MLP (from {v4_path}): BAcc={res['mlp_overall_bacc']}, FPR={res['mlp_overall_fpr']}, Normal FPR={res['mlp_normal_fpr']}")
