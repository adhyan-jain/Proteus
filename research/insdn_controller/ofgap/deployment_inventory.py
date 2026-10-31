"""Per-deployment, per-class inventory of strictly labelled controller windows (W=1 s).

Usage: python deployment_inventory.py <feat_dir> <out_json>

Reports, for every (deployment, class) cell: captures, windows, kept windows, attack windows and the attack-free
kept windows split into non-empty / empty (empty = no PacketIn at all). Also the share of each class in the pooled
attack windows. The within-attack-session metric of exp_ctrl2 uses only non-empty windows.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import exp_ctrl2  # noqa: E402


def main():
    feat_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    caps = exp_ctrl2.load(feat_dir, 1.0, "strict")
    cell = collections.defaultdict(collections.Counter)
    for c in caps:
        k = f"{c['dep']}|{c['label']}"
        y, keep, ne = c["y"], c["keep"], c["nonempty"]
        cell[k]["captures"] += 1
        cell[k]["windows"] += len(y)
        cell[k]["kept"] += int(keep.sum())
        cell[k]["attack"] += int((keep & (y == 1)).sum())
        cell[k]["attack_free_nonempty"] += int((keep & (y == 0) & ne).sum())
        cell[k]["attack_free_empty"] += int((keep & (y == 0) & ~ne).sum())
        cell[k]["attack_free_nonempty_with_ip"] += int((keep & (y == 0) & ne & (c["X"][:, 7] > 0)).sum())
    total_attack = sum(v["attack"] for v in cell.values())
    by_class, by_dep = collections.Counter(), collections.Counter()
    for k, v in cell.items():
        dep, lab = k.split("|")
        by_class[lab] += v["attack"]
        by_dep[dep] += v["attack"]
    ae = [v for k, v in cell.items() if not k.startswith("normal|")]
    res = {"cells": {k: dict(v) for k, v in sorted(cell.items())},
           "total_attack_windows": total_attack,
           "total_kept_windows": sum(v["kept"] for v in cell.values()),
           "attack_share_by_class_pct": {k: round(100.0 * v / total_attack, 1) for k, v in sorted(by_class.items())},
           "attack_windows_by_deployment": dict(by_dep),
           "within_attack_sessions": {
               "attack_free_kept_nonempty": sum(v["attack_free_nonempty"] for v in ae),
               "attack_free_kept_empty": sum(v["attack_free_empty"] for v in ae),
               "attack_free_nonempty_with_ip_packetin": sum(v["attack_free_nonempty_with_ip"] for v in ae)}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res["attack_share_by_class_pct"]), res["within_attack_sessions"])


if __name__ == "__main__":
    main()
