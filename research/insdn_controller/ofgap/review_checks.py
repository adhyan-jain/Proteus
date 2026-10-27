"""Checks demanded by the second hostile review: trivial within-session baselines and confound-probe cell sizes.

Usage: review_checks.py <feat_dir> <out_json>
 - within-session (attack captures, windows with >=1 PacketIn): BAcc of the trivial rules "any IP PacketIn"
   (distinct source IPs > 0) and "any PacketIn", pooled and macro over captures, under strict and iprule labels
 - probe cells (>=5 background PacketIns): windows and captures per class for D1/D2, and the share of D1
   attack-session windows that contain unmatched-IP PacketIns
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import FEATS, LABCOLS  # noqa: E402
from exp_ctrl2 import load  # noqa: E402

d, out = Path(sys.argv[1]), Path(sys.argv[2])
LC = {k: i for i, k in enumerate(LABCOLS)}
SRC = FEATS.index("pin_src_ip")
R = {}


def bacc(y, p):
    if not (y == 1).any() or not (y == 0).any():
        return float("nan")
    return float((p[y == 1].mean() + (~p[y == 0]).mean()) / 2)


for W in (1.0, 5.0):
    for scheme in ("strict", "iprule"):
        caps = load(d, W, scheme)
        cell = {}
        for rule, name in ((lambda X: X[:, SRC] > 0, "any_ip_packet_in"), (lambda X: X[:, 0] > 0, "any_packet_in")):
            ys, ps, per = [], [], []
            for c in caps:
                if c["session"] != 1:
                    continue
                m = c["keep"] & c["nonempty"]
                y, p = c["y"][m], rule(c["X"][m])
                ys.append(y), ps.append(p)
                b = bacc(y, p)
                if not np.isnan(b):
                    per.append(b)
            y, p = np.concatenate(ys), np.concatenate(ps)
            cell[name] = {"bacc_pooled": bacc(y, p), "bacc_macro_captures": float(np.mean(per)) if per else None,
                          "positives": int((y == 1).sum()), "negatives": int((y == 0).sum()),
                          "captures_with_both_classes": len(per)}
        neg_total = neg_noip = 0
        for c in caps:
            if c["session"] == 1:
                m = c["keep"] & c["nonempty"] & (c["y"] == 0)
                neg_total += int(m.sum())
                neg_noip += int((c["X"][m, SRC] == 0).sum())
        cell["attack_capture_negatives_nonempty"] = {"total": neg_total, "with_zero_ip_packet_in": neg_noip}
        R[f"within_session_W{W:g}_{scheme}"] = cell

meta = json.loads((d / "meta.json").read_text())
for W in (1.0, 5.0):
    caps = load(d, W, "strict")
    tot = {"D1_attack_windows": 0, "D1_attack_windows_with_unmatched_ip": 0, "D1_normal_windows": 0,
           "D2_attack_free_windows": 0, "D2_normal_windows": 0}
    capsets = {"D1_attack": set(), "D2_attack_free": set()}
    for (cid, m), c in zip(sorted(meta.items()), caps):
        L = np.load(d / f"{cid}_W{W:g}_lab.npy")
        ok = c["Xb"][:, 0] >= 5
        if c["session"] == 1:
            tot["D1_attack_windows"] += int(ok.sum())
            tot["D1_attack_windows_with_unmatched_ip"] += int((ok & (L[:, LC["unm_ip"]] > 0)).sum())
            if ok.any():
                capsets["D1_attack"].add(cid)
            f = ok & (c["y"] == 0) & c["keep"]
            tot["D2_attack_free_windows"] += int(f.sum())
            if f.any():
                capsets["D2_attack_free"].add(cid)
        else:
            tot["D1_normal_windows"] += int(ok.sum())
            tot["D2_normal_windows"] += int(ok.sum())
    tot["captures_contributing"] = {k: len(v) for k, v in capsets.items()}
    R[f"probe_cells_W{W:g}_strict"] = tot

out.write_text(json.dumps(R, indent=1))
print(json.dumps(R, indent=1))
