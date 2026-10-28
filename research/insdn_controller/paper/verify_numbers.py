"""Re-verify headline numbers quoted in paper/*.tex against results/*.json. Exit 1 on any mismatch.
Usage: python verify_numbers.py (from anywhere)"""
import json
import re
import sys
from pathlib import Path

H = Path(__file__).parent
R = H.parent / "results"
tex = "".join((H / f).read_text() for f in ("main.tex", "live_section.tex")).replace("\\,", "").replace("$", "")
J = lambda n: json.load(open(R / n))  # noqa: E731
fm, one, l3, xg = J("flowmod_matches.json"), J("live_modes_v4_one10.json"), J("live_modes_v4_linear3.json"), J("v4_strict_W5_xgb.json")
st, hs = J("stock_ryu_flowmods.json"), J("hostside_xgb.json")
S = lambda d, k: d["summary"][k]  # noqa: E731
checks = [
    ("FlowMods total", fm["flowmods"], "3827"),
    ("FlowMods MAC-pair", fm["total_by_match_structure"]["in_port|eth_dst|eth_src"], "3811"),
    ("FlowMods eth_type", fm["total_by_match_structure"]["eth_type"], "16"),
    ("1sw MAC TCP PacketIn", round(S(one, "mac")["packet_in_tcp"]["mean"], 1), "12.3"),
    ("1sw 5tuple TCP PacketIn", round(S(one, "fivetuple")["packet_in_tcp"]["mean"]), "10422"),
    ("1sw short TCP PacketIn", round(S(one, "fivetuple_short")["packet_in_tcp"]["mean"]), "10392"),
    ("1sw entries/reply 10s", round(S(one, "fivetuple")["fivetuple_entries_per_reply"]["mean"], 1), "153.1"),
    ("1sw entries/reply 2s", round(S(one, "fivetuple_short")["fivetuple_entries_per_reply"]["mean"], 1), "36.9"),
    ("3sw MAC TCP PacketIn", round(S(l3, "mac")["packet_in_tcp"]["mean"], 1), "18.0"),
    ("3sw 5tuple TCP PacketIn", round(S(l3, "fivetuple")["packet_in_tcp"]["mean"]), "10881"),
    ("XGB BAcc", round(xg["A_grouped_cv"]["xgb_all_history"]["bacc"]["mean"], 3), "0.952"),
    ("Linear BAcc W5", round(xg["A_grouped_cv"]["linear_all_history"]["bacc"]["mean"], 3), "0.961"),
    ("MLP BAcc W5", round(xg["A_grouped_cv"]["mlp_all"]["bacc"]["mean"], 3), "0.958"),
    ("stock FlowMods", st["flowmods"], "91"),
    ("stock MAC-pair FlowMods", st["total_by_match_structure"]["in_port|eth_dst|eth_src"], "86"),
    ("stock PacketIn mean", round(sum(st["packet_in_per_run"]) / len(st["packet_in_per_run"]), 1), "73.6"),
    ("host-side rows", hs["rows"], "343889"),
    ("host-side BAcc", round(hs["bacc_mean"], 4), "0.9998"),
    ("host-side features", hs["features"], "78"),
]
bad = 0
for name, val, quoted in checks:
    ok = str(val) == quoted and quoted in tex
    bad += not ok
    print(("OK  " if ok else "FAIL"), name, "json=%s paper=%s" % (val, quoted))
sys.exit(1 if bad else 0)
