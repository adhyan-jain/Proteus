"""Forwarding-mode study: per-run controller observations -> results/live_modes_v2.json and paper/live_table.tex.

Usage: live_table.py <campaign_dir> <out_json> <out_tex>
Per capture (one run of one forwarding mode, benign traffic only): PacketIns by embedded protocol, FlowMods,
flow-statistics entry observations by match structure. Per mode: mean and 95% t-interval over repeats.
"""
import collections
import json
import sys
from pathlib import Path

import dpkt
import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ofgap"))
from ctrlfeat import _pin_frame, extract  # noqa: E402
from ofparse import of_messages  # noqa: E402

camp, out_json, out_tex = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
NOTE = sys.argv[4] if len(sys.argv) > 4 else ""
LABEL = sys.argv[5] if len(sys.argv) > 5 else "tab:live"
FIVE = "in_port|eth_type|ipv4_src|ipv4_dst|ip_proto|tcp_src|tcp_dst"
MAC = "in_port|eth_src|eth_dst"
runs = collections.defaultdict(list)
for f in sorted(camp.glob("*.pcap")):
    mode = f.stem.rsplit("_s", 1)[0]
    X, inv, _ = extract(f, 1.0)
    pin = collections.Counter()
    for _ts, d, _v, t, b in of_messages(f):
        if t == 10 and d == "to_ctrl":
            e = _pin_frame(b)
            ip = e.data if e is not None else None
            pin["tcp" if isinstance(getattr(ip, "data", None), dpkt.tcp.TCP) else "other"] += 1
    ms = {"|".join(k): v for k, v in inv["match_sets"].items()}
    replies = max(len(inv["stats_times"]), 1)
    runs[mode].append({
        "file": f.name, "seconds": len(X), "match_sets": ms, "packet_in_total": inv["pin"], "packet_in_tcp": pin["tcp"],
        "flow_mods": inv["fmod"], "stats_replies": len(inv["stats_times"]),
        "fivetuple_entries_per_reply": sum(v for k, v in ms.items() if "ipv4_src" in k) / replies, "macpair_entries_per_reply": ms.get(MAC, 0) / replies,
        "parser_desyncs": inv["parser"]["desyncs"], "parser_dropped_bytes": inv["parser"]["dropped_bytes"]})


def ci(v):
    v = np.asarray(v, float)
    h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
    return {"mean": float(v.mean()), "ci95": float(h), "n": int(len(v))}


KEYS = ["packet_in_tcp", "packet_in_total", "flow_mods", "macpair_entries_per_reply", "fivetuple_entries_per_reply"]
summary = {m: {k: ci([r[k] for r in rs]) for k in KEYS} for m, rs in runs.items()}
out_json.write_text(json.dumps({"summary": summary, "runs": runs}, indent=1))

names = {"mac": "MAC-pair (as ONOS in InSDN)", "fivetuple": "5-tuple, 10\\,s idle",
         "fivetuple_short": "5-tuple, 2\\,s idle"}
rows = []
for m in ("mac", "fivetuple", "fivetuple_short"):
    s = summary[m]
    cells = [f"{s[k]['mean']:.1f}{{\\scriptsize$\\pm${s[k]['ci95']:.1f}}}" for k in KEYS]
    rows.append(names[m] + " & " + " & ".join(cells) + " \\\\")
n = summary["mac"]["packet_in_tcp"]["n"]
tex = ("\\begin{table*}[t]\n\\caption{Forwarding application vs.\\ what the controller observes: benign traffic from the same generator and seeds "
       f"(5 hosts $\\rightarrow$ 1 HTTP server, plus pings), 1-switch Mininet/Ryu testbed, $\\sim$99\\,s capture per run, {n} runs per "
       "mode, mean{\\scriptsize$\\pm$}95\\% CI. Entries = flow entries returned per flow-statistics reply "
       f"(1\\,s polling). {NOTE}}}\n"
       f"\\label{{{LABEL}}}\n\\centering\\small\n"
       "\\begin{tabular}{lccccc}\n\\toprule\n"
       "Mode & TCP PacketIns & All PacketIns & FlowMods & MAC-pair entries & IP-specific entries \\\\\n\\midrule\n"
       + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table*}\n")
out_tex.write_text(tex)
print(json.dumps({m: {k: round(v["mean"], 2) for k, v in s.items()} for m, s in summary.items()}, indent=1))
print("runs per mode:", {m: len(r) for m, r in runs.items()},
      "parser desyncs:", sum(r["parser_desyncs"] for rs in runs.values() for r in rs))
