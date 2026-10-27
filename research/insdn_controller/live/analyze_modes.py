"""What an IDS can observe under each forwarding mode: summarise captured control channels.

Usage: analyze_modes.py <pcap_dir> <out.json>
Per capture: PacketIn rate, FlowMod count, flow-stats match structures and entry counts, parser reliability.
Aggregates per mode (mean +/- 95% t-interval over repeats).
"""
import collections
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ofgap"))
from ctrlfeat import extract  # noqa: E402

root, out = Path(sys.argv[1]), Path(sys.argv[2])
runs = collections.defaultdict(list)
for f in sorted(root.glob("*.pcap")):
    mode = f.stem.rsplit("_s", 1)[0]
    X, inv, _ = extract(f, 1.0)
    dur = max(len(X), 1)
    ms = {"|".join(k): v for k, v in inv["match_sets"].items()}
    ent = int(sum(inv["match_sets"].values()))
    runs[mode].append({
        "file": f.name, "seconds": dur, "packet_in_per_s": inv["pin"] / dur, "flow_mods": inv["fmod"],
        "stats_replies": len(inv["stats_times"]), "entry_observations": ent,
        "entry_obs_per_reply": ent / max(len(inv["stats_times"]), 1), "match_sets": ms, "parser": inv["parser"]})


def ci(v):
    v = np.asarray(v, float)
    h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
    return {"mean": float(v.mean()), "ci95": float(h), "n": len(v)}


summary = {m: {k: ci([r[k] for r in rs]) for k in ("packet_in_per_s", "flow_mods", "entry_obs_per_reply")}
           | {"match_structures_seen": sorted({k for r in rs for k in r["match_sets"]})} for m, rs in runs.items()}
out.write_text(json.dumps({"summary": summary, "runs": runs}, indent=1))
print(json.dumps(summary, indent=1))
