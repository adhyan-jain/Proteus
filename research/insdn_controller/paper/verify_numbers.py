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
st, hs, pi = J("stock_ryu_flowmods.json"), J("hostside_xgb.json"), J("protocol_inflation.json")
ai, ac, lit = J("protocol_audit_insdn.json"), J("protocol_audit_cicids2017.json"), json.load(open(R.parent / "literature_check.json"))
lp = lit["papers"]
insdn_read = [p for p in lp if p["read"] and "UNSW" not in str(p.get("dataset"))]  # the one read paper not on InSDN/SDN data is GRU-NTM (UNSW-NB15, BoT-IoT)
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
    ("split A random", round(pi["A_random_flow_split"]["mean"], 4), "0.9998"),
    ("split B held-out hosts", round(pi["B_source_ip_grouped_split"]["mean"], 3), "0.907"),
    ("split B CI", round(pi["B_source_ip_grouped_split"]["ci95"], 3), "0.085"),
    ("split B worst", round(min(pi["B_source_ip_grouped_split"]["per_seed"]), 2), "0.66"),
    ("split C time-ordered", round(pi["C_time_ordered_split"]["mean"], 4), "0.9997"),
    # evaluation-validity audit (protocol_audit_*.json)
    ("audit InSDN A", round(ai["A_random_flow_split"]["mean"], 4), "0.9998"),
    ("audit InSDN B", round(ai["B_source_ip_grouped_split"]["mean"], 3), "0.907"),
    ("audit InSDN B CI", round(ai["B_source_ip_grouped_split"]["ci95"], 3), "0.085"),
    ("audit InSDN B worst", round(min(ai["B_source_ip_grouped_split"]["per_seed"]), 2), "0.66"),
    ("audit InSDN C", round(ai["C_time_ordered_split"]["mean"], 4), "0.9997"),
    ("audit InSDN D >= 0.9999", round(ai["D_identifier_only_random_split"]["mean"], 4) >= 0.9999 and round(ac["D_identifier_only_random_split"]["mean"], 4) >= 0.9999, "0.9999"),
    ("audit InSDN E pct", round(100 * ai["E_test_rows_duplicating_train_row_splitA"]["mean"], 1), "48.7"),
    ("audit InSDN rows", ai["rows"], "343889"),
    ("audit CICIDS A", round(ac["A_random_flow_split"]["mean"], 4), "0.9917"),
    ("audit CICIDS B", round(ac["B_source_ip_grouped_split"]["mean"], 3), "0.641"),
    ("audit CICIDS B CI", round(ac["B_source_ip_grouped_split"]["ci95"], 3), "0.056"),
    ("audit CICIDS C", round(ac["C_time_ordered_split"]["mean"], 3), "0.719"),
    ("audit CICIDS E pct", round(100 * ac["E_test_rows_duplicating_train_row_splitA"]["mean"], 1), "20.3"),
    ("audit CICIDS rows", ac["rows"], "2100814"),
    ("audit CICIDS A-B gap pts", round(100 * (ac["A_random_flow_split"]["mean"] - ac["B_source_ip_grouped_split"]["mean"])), "35"),
    ("audit InSDN A-B gap pts", round(100 * (ai["A_random_flow_split"]["mean"] - ai["B_source_ip_grouped_split"]["mean"])), "nine"),
    # literature audit counts
    ("lit papers examined", len(lp), "12"),
    ("lit papers read in full", sum(p["read"] for p in lp), "10"),
    ("lit InSDN papers read in full", len(insdn_read), "nine"),
    ("lit read InSDN, none grouped", sum(bool(p.get("grouped")) for p in insdn_read), "none reports a host-grouped"),
    ("lit read InSDN, ids as inputs", sum(bool(p.get("identifiers_as_features")) for p in insdn_read), "three"),
]
WORDS = {"nine": 9, "three": 3, "none": 0}
bad = 0
for name, val, quoted in checks:
    num = WORDS.get(quoted.split()[0], quoted)  # quoted word -> number it stands for
    ok = (val is True or str(val) == str(num)) and quoted in tex
    bad += not ok
    print(("OK  " if ok else "FAIL"), name, "json=%s paper=%s" % (val, quoted))
sys.exit(1 if bad else 0)
