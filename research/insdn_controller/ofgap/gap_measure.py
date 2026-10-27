"""Granularity gap: what InSDN labels (5-tuple flows at the target) vs what ONOS observes (control channel).

For each scenario directory with both a target-side capture and an ONOS_* capture:
  target: packets, distinct 5-tuples (unidirectional), distinct src IPs
  controller: PACKET_IN count, FLOW_MOD count, distinct forwarding entries in flow-stats replies,
              their match-field sets, median flow-stats poll gap
Usage: gap_measure.py <ex_root> <out.json>
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import extract, label_of  # noqa: E402
from ofsim import _iter_packets, _key  # noqa: E402


def target_stats(p: Path):
    n, tuples, srcs = 0, set(), set()
    for _ts, ip in _iter_packets(p):
        k, _ = _key(ip)
        if 6653 in (k[3], k[4]) or 6633 in (k[3], k[4]):
            continue
        n += 1
        tuples.add(k)
        srcs.add(k[0])
    return dict(packets=n, five_tuples=len(tuples), src_ips=len(srcs))


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    R = {}
    for d in sorted({p.parent for p in root.rglob("*.pcap*")}):
        files = sorted(p for p in d.iterdir() if p.is_file())
        onos = [f for f in files if "onos" in f.name.lower()]
        tgt = [f for f in files if "onos" not in f.name.lower()]
        if not onos:
            continue
        ctrl = {"packet_in": 0, "flow_mod": 0, "stats_replies": 0, "entries": collections.Counter(),
                "gaps": []}
        for f in onos:
            _X, inv, _L = extract(f, 5.0)
            ctrl["packet_in"] += inv["pin"]
            ctrl["flow_mod"] += inv["fmod"]
            ctrl["stats_replies"] += len(inv["stats_times"])
            ctrl["entries"].update(inv["match_sets"])
            ctrl["gaps"] += list(np.diff(sorted(inv["stats_times"])))
        t = {"packets": 0, "five_tuples": 0, "src_ips": 0}
        for f in tgt:
            for k, v in target_stats(f).items():
                t[k] += v
        R[str(d.relative_to(root))] = {
            "label": label_of(onos[0]), "target_files": [f.name for f in tgt], "onos_files": [f.name for f in onos],
            "target": t,
            "controller": {"packet_in": ctrl["packet_in"], "flow_mod": ctrl["flow_mod"],
                           "stats_replies": ctrl["stats_replies"],
                           "entry_observations_by_match": {"|".join(k): v for k, v in ctrl["entries"].items()},
                           "stats_gap_median_s": float(np.median(ctrl["gaps"])) if ctrl["gaps"] else None},
            "packet_in_per_target_packet": ctrl["packet_in"] / t["packets"] if t["packets"] else None,
        }
        print(d.name, R[str(d.relative_to(root))]["target"], ctrl["packet_in"], flush=True)
    out.write_text(json.dumps(R, indent=1))


if __name__ == "__main__":
    main()
