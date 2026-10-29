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
DL, RP, LH = J("dedup_ladder.json"), J("replicate_papers.json"), J("leave_one_host_out.json")
st, hs, pi = J("stock_ryu_flowmods.json"), J("hostside_xgb.json"), J("protocol_inflation.json")
ai, ac, lit = J("protocol_audit_insdn.json"), J("protocol_audit_cicids2017.json"), json.load(open(R.parent / "literature_check.json"))
rr = J("recipe_replication.json")
lp = lit["papers"]
insdn_read = [p for p in lp if p["read"] and "UNSW" not in str(p.get("dataset"))]  # the one read paper not on InSDN/SDN data is GRU-NTM (UNSW-NB15, BoT-IoT)
RECIPES = ("numeric", "numeric+port", "ids_all", "top15_mi_ids")
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
    ("dedup random", round(DL["random|dedup"]["mean"], 4), "0.9998"),
    ("dedup rows after", f"{DL['rows_after_dedup']:,}", "184,607"),
    ("class-covered grouped src ip", round(DL["grouped_src_ip_class_covered|all_rows"]["result"]["mean"], 3), "0.939"),
    ("class-covered grouped src ip dedup", round(DL["grouped_src_ip_class_covered|dedup"]["result"]["mean"], 3), "0.812"),
    ("triple grouped", round(DL["grouped_src_dst_dport_triple_class_covered|all_rows"]["result"]["mean"], 3), "0.961"),
    ("triple grouped dedup", round(DL["grouped_src_dst_dport_triple_class_covered|dedup"]["result"]["mean"], 3), "0.984"),
    ("SDNGuardStack random", round(RP["paper1"]["a_random_ids|train_only"]["acc"]["mean"], 4), "0.9999"),
    ("SDNGuardStack grouped lo", round(RP["paper1"]["b_grouped_ids|train_only"]["acc"]["mean"], 2), "0.72"),
    ("SDNGuardStack grouped hi", round(RP["paper1"]["b_grouped_ids|all_rows"]["acc"]["mean"], 2), "0.78"),
    ("LOHO distinct ips", f"{LH['distinct_src_ips']:,}", "122,868"),
    ("LOHO single flow", f"{LH['single_flow_src_ips']:,}", "122,307"),
    ("LOHO big hosts", "eight hosts" if LH["hosts_ge_500_flows"] == 8 else "MISMATCH", "eight hosts"),
    ("LOHO big host rows", f"{LH['rows_in_hosts_ge_500']:,}", "215,404"),
    ("LOHO main attacker recall", round(100 * LH["hosts"]["200.175.2.130"]["recall_attack"], 1), "%.1f" % (100 * LH["hosts"]["200.175.2.130"]["recall_attack"])),
    ("LOHO main attacker DoS", round(100 * LH["hosts"]["200.175.2.130"]["recall_by_class"]["DoS"], 1), "%.1f" % (100 * LH["hosts"]["200.175.2.130"]["recall_by_class"]["DoS"])),
    ("LOHO benign host fpr", round(100 * LH["hosts"]["192.168.20.133"]["fpr_benign"], 1), "%.1f" % (100 * LH["hosts"]["192.168.20.133"]["fpr_benign"])),
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
    # recipe replication (recipe_replication.json)
    ("recipe random min BAcc", round(min(rr[f"{r}|random"]["binary_bacc"]["mean"] for r in RECIPES), 4), "0.9998"),
    ("recipe random min 8-class", round(min(rr[f"{r}|random"]["multiclass_acc"]["mean"] for r in RECIPES), 4), "0.9991"),
    ("recipe grouped min BAcc", round(min(rr[f"{r}|grouped_src_ip"]["binary_bacc"]["mean"] for r in RECIPES), 3), "0.856"),
    ("recipe grouped max BAcc", round(max(rr[f"{r}|grouped_src_ip"]["binary_bacc"]["mean"] for r in RECIPES), 3), "0.943"),
    ("recipe grouped min 8-class", round(min(rr[f"{r}|grouped_src_ip"]["multiclass_acc"]["mean"] for r in RECIPES), 3), "0.687"),
    ("recipe grouped max 8-class", round(max(rr[f"{r}|grouped_src_ip"]["multiclass_acc"]["mean"] for r in RECIPES), 3), "0.835"),
    ("recipe widest CI 8-class", round(max(rr[f"{r}|grouped_src_ip"]["multiclass_acc"]["ci95"] for r in RECIPES), 3), "0.241"),
    ("recipe ids grouped BAcc", round(rr["ids_all|grouped_src_ip"]["binary_bacc"]["mean"], 3), "0.941"),
    ("recipe seeds", min(rr[k][m]["n"] for k in rr if "|" in k for m in ("binary_bacc", "multiclass_acc")), "10"),
    ("recipe unseen-class test rows", max(rr[k]["test_rows_in_unseen_class"]["mean"] for k in rr if "|" in k), "0.0"),
    ("recipe MI picks ids", all(x in rr["top15_mi_selected_on_full_data"] for x in ("Flow ID", "Src IP", "Dst IP")), "Flow ID, Src IP and Dst IP"),
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
