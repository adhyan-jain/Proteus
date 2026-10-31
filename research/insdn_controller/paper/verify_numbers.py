"""Re-verify headline numbers quoted in paper/*.tex against results/*.json. Exit 1 on any mismatch.
Usage: python verify_numbers.py (from anywhere)"""
import json
import re
import sys
from pathlib import Path

H = Path(__file__).parent
R = H.parent / "results"
tex = "".join((H / f).read_text() for f in ("main.tex", "live_section.tex", "table_deployment.tex", "table_recon.tex", "table_literature.tex")).replace("\\,", "").replace("$", "")
J = lambda n: json.load(open(R / n))  # noqa: E731
fm, one, l3, xg = J("flowmod_matches.json"), J("live_modes_v4_one10.json"), J("live_modes_v4_linear3.json"), J("v4_strict_W5_xgb.json")
DL, RP, LH, LC = J("dedup_ladder.json"), J("replicate_papers.json"), J("leave_one_host_out.json"), J("leave_one_host_out_cicids2017.json")
st, hs, pi = J("stock_ryu_flowmods.json"), J("hostside_xgb.json"), J("protocol_inflation.json")
ai, ac, lit = J("protocol_audit_insdn.json"), J("protocol_audit_cicids2017.json"), json.load(open(R.parent / "literature_check.json"))
rr = J("recipe_replication.json")
fta, pr, haa = J("flowtable_audit.json"), J("packetin_reconstruction.json"), J("host_assignment_audit.json")
ose = J("operational_stream_evaluation.json")
di, sb = J("deployment_inventory.json"), J("session_identity_baseline.json")
V4 = J("v4_strict_W1.json")["A_grouped_cv"]
C = di["cells"]
MSP = [k for k in C if k.startswith("metasploitable|")]
OVSC = [k for k in C if k.startswith("ovs|")]
ZERO_FM = [k for k, v in json.load(open(R / "flowmod_matches.json"))["per_capture"].items() if not v]
ZERO_FM_MAC = [fta["per_capture"][k]["mac_pair_entries"] for k in ZERO_FM]
SB = lambda rule, m: sb[rule][m]["mean"]  # noqa: E731
ROW = lambda m: (f"{m['bacc']['mean']:.3f}{{\\scriptsize\\pm{m['bacc']['ci95']:.3f}}} & "  # noqa: E731
                 f"{m['recall']['mean']:.3f} & {m['fpr']['mean']:.3f}")
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
    ("audit InSDN B seed 0", f"{ai['B_source_ip_grouped_split']['per_seed'][0]:.3f}", "0.786"),
    ("audit InSDN B seed 1", f"{ai['B_source_ip_grouped_split']['per_seed'][1]:.3f}", "0.660"),
    ("audit InSDN B seed 2", f"{ai['B_source_ip_grouped_split']['per_seed'][2]:.3f}", "0.939"),
    ("audit InSDN B seed 3", f"{ai['B_source_ip_grouped_split']['per_seed'][3]:.3f}", "1.000"),
    ("audit InSDN B seed 4", f"{ai['B_source_ip_grouped_split']['per_seed'][4]:.3f}", "0.859"),
    ("audit InSDN B seed 5", f"{ai['B_source_ip_grouped_split']['per_seed'][5]:.3f}", "0.996"),
    ("audit InSDN B seed 6", f"{ai['B_source_ip_grouped_split']['per_seed'][6]:.3f}", "0.998"),
    ("audit InSDN B seed 7", f"{ai['B_source_ip_grouped_split']['per_seed'][7]:.3f}", "0.837"),
    ("audit InSDN B seed 8", f"{ai['B_source_ip_grouped_split']['per_seed'][8]:.3f}", "1.000"),
    ("audit InSDN B seed 9", f"{ai['B_source_ip_grouped_split']['per_seed'][9]:.3f}", "0.999"),
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
    ("SDNGuardStack train_only seed 0", f"{RP['paper1']['b_grouped_ids|train_only']['acc']['per_seed'][0]:.2f}", "0.24"),
    ("SDNGuardStack train_only seed 1", f"{RP['paper1']['b_grouped_ids|train_only']['acc']['per_seed'][1]:.2f}", "0.73"),
    ("SDNGuardStack train_only seed 2", f"{RP['paper1']['b_grouped_ids|train_only']['acc']['per_seed'][2]:.2f}", "1.00"),
    ("SDNGuardStack train_only seed 3", f"{RP['paper1']['b_grouped_ids|train_only']['acc']['per_seed'][3]:.2f}", "0.66"),
    ("SDNGuardStack train_only seed 4", f"{RP['paper1']['b_grouped_ids|train_only']['acc']['per_seed'][4]:.2f}", "0.99"),
    ("SDNGuardStack all_rows seed 0", f"{RP['paper1']['b_grouped_ids|all_rows']['acc']['per_seed'][0]:.2f}", "0.33"),
    ("SDNGuardStack all_rows seed 1", f"{RP['paper1']['b_grouped_ids|all_rows']['acc']['per_seed'][1]:.2f}", "0.99"),
    ("SDNGuardStack all_rows seed 2", f"{RP['paper1']['b_grouped_ids|all_rows']['acc']['per_seed'][2]:.2f}", "1.00"),
    ("SDNGuardStack all_rows seed 3", f"{RP['paper1']['b_grouped_ids|all_rows']['acc']['per_seed'][3]:.2f}", "0.62"),
    ("SDNGuardStack all_rows seed 4", f"{RP['paper1']['b_grouped_ids|all_rows']['acc']['per_seed'][4]:.2f}", "0.98"),
    ("LOHO distinct ips", f"{LH['distinct_src_ips']:,}", "122,868"),
    ("LOHO single flow", f"{LH['single_flow_src_ips']:,}", "122,307"),
    ("LOHO big hosts", "eight hosts" if LH["hosts_ge_500_flows"] == 8 else "MISMATCH", "eight hosts"),
    ("LOHO big host rows", f"{LH['rows_in_hosts_ge_500']:,}", "215,404"),
    ("LOHO main attacker recall", round(100 * LH["hosts"]["200.175.2.130"]["recall_attack"], 1), "%.1f" % (100 * LH["hosts"]["200.175.2.130"]["recall_attack"])),
    ("LOHO main attacker DoS", round(100 * LH["hosts"]["200.175.2.130"]["recall_by_class"]["DoS"], 1), "%.1f" % (100 * LH["hosts"]["200.175.2.130"]["recall_by_class"]["DoS"])),
    ("LOHO benign host fpr", round(100 * LH["hosts"]["192.168.20.133"]["fpr_benign"], 1), "%.1f" % (100 * LH["hosts"]["192.168.20.133"]["fpr_benign"])),
    ("LOHO CIC ips", LC["distinct_src_ips"], "48"),
    ("LOHO CIC main recall", round(100 * LC["hosts"]["172.16.0.1"]["recall_attack"], 1), "28.3"),
    ("LOHO CIC main fpr", round(100 * LC["hosts"]["172.16.0.1"]["fpr_benign"], 1), "54.0"),
    ("LOHO CIC bot lo", round(100 * min(LC["hosts"][k]["recall_attack"] for k in LC["hosts"] if k.startswith("192.168.10.") and LC["hosts"][k]["recall_attack"] not in (None, 0.0)), 1), "23.4"),
    ("LOHO CIC bot hi", round(100 * max(LC["hosts"][k]["recall_attack"] for k in LC["hosts"] if k.startswith("192.168.10.") and LC["hosts"][k]["recall_attack"] is not None), 1), "43.5"),
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
    ("lit papers read in full (word)", sum(p["read"] for p in lp), "ten"),
    ("lit read InSDN, none grouped", sum(bool(p.get("grouped")) for p in insdn_read), "none reports a host-grouped"),
    ("lit read InSDN, ids as inputs", sum(bool(p.get("identifiers_as_features")) for p in insdn_read), "three"),
    # flowtable decode (flowtable_audit.json)
    ("flowtable ipv4 punt entries", fta["eth_type_breakdown"]["0x800"], "20116"),
    ("flowtable ipv4 punt caps", fta["captures_with_ipv4_controller_punt"], "44"),
    # packetin software reconstruction (packetin_reconstruction.json; table_recon.tex quotes counts with thousands commas)
    ("recon DDoS 100pct single-pkt", pr["OVS_DDoS"]["pct_single_packet_flows"], "100.0"),
    ("recon DDoS total flows", f"{pr['OVS_DDoS']['distinct_reconstructed_flows']:,}", "17,566"),
    ("recon Probe pct single-pkt", pr["OVS_Probe"]["pct_single_packet_flows"], "97.3"),
    ("recon MS2 DoS pct single-pkt", pr["MS2_DoS"]["pct_single_packet_flows"], "7.1"),
    ("recon MS2 DoS matching 5tuples", pr["MS2_DoS"]["matching_5tuples"], "494"),
    ("recon MS2 DoS matched share", pr["MS2_DoS"]["matched_share_of_reconstructed_pct"] == 1.7, "covering 1.7\\%"),
    ("recon MS2 Probe pct single-pkt", pr["MS2_Probe"]["pct_single_packet_flows"], "0.6"),
    ("recon MS2 Probe matching 5tuples", f"{pr['MS2_Probe']['matching_5tuples']:,}", "13,214"),
    ("recon Normal pct single-pkt", pr["Normal_1"]["pct_single_packet_flows"], "35.3"),
    ("recon Normal matching 5tuples", pr["Normal_1"]["matching_5tuples"], "140"),
    ("recon DoS pkt spearman", f"{pr['MS2_DoS']['packet_count_spearman']:.2f}", "0.24"),
    ("recon DoS pkt spearman in text", f"{pr['MS2_DoS']['packet_count_spearman']:.2f}" == "0.24", "rho=0.24"),
    ("recon Probe pkt spearman", f"{pr['MS2_Probe']['packet_count_spearman']:.2f}" == "0.86", "rho=0.86"),
    ("recon Normal pkt spearman", f"{pr['Normal_1']['packet_count_spearman']:.2f}" == "0.94", "rho=0.94"),
    ("recon Normal duration spearman", f"{pr['Normal_1']['duration_spearman']:.2f}" == "0.98", "0.98 on the benign capture"),
    ("recon DoS/Probe duration spearman",
     (f"{pr['MS2_DoS']['duration_spearman']:.2f}", f"{pr['MS2_Probe']['duration_spearman']:.2f}") == ("-0.27", "-0.11"),
     "-0.27 on DoS and -0.11 on probing"),
    ("recon packet-total ratios",
     f"{round(100 * pr['MS2_DoS']['packet_sum_ratio_recon_over_csv'])}\\% (DoS) and "
     f"{round(100 * pr['Normal_1']['packet_sum_ratio_recon_over_csv'])}\\% (benign)", "38\\% (DoS) and 45\\% (benign)"),
    ("recon Probe packet-total ratio", abs(pr["MS2_Probe"]["packet_sum_ratio_recon_over_csv"] - 1.0) < 0.005, "ratio 1.00"),
    # host assignment audit (host_assignment_audit.json)
    ("host audit seed 0 test frac", round(100 * haa["seeds"][0]["test_frac"], 1), "43.7"),
    ("host audit seed 1 test frac", round(100 * haa["seeds"][1]["test_frac"], 1), "57.1"),
    ("host audit seed 2 test frac", round(100 * haa["seeds"][2]["test_frac"], 1), "22.2"),
    ("host audit seed 2 bacc", round(haa["seeds"][2]["score_bacc"], 3), "0.939"),
    # operational stream evaluation (operational_stream_evaluation.json)
    ("operational normal windows", f"{ose['normal_windows_total']:,}", "33,283"),
    ("operational normal ip windows", f"{ose['normal_windows_with_ip']:,}", "25,810"),
    ("operational normal ip fpr", ose["normal_windows_ip_fpr_pct"], "77.5"),
    ("operational normal ip fpr 3dp", f"{ose['normal_windows_with_ip'] / ose['normal_windows_total']:.3f}" == "0.775", "normal-session FPR = 0.775"),
    ("operational strict trivial bacc", f"{ose['strict_trivial_rule_bacc']:.4f}", "0.6360"),
    ("operational raw trivial bacc", ose["raw_stream_trivial_bacc"], "0.4889"),
    # deployment inventory (deployment_inventory.json, table_deployment.tex)
    ("attack windows total", di["total_attack_windows"], "2589"),
    ("probe share of attack windows", di["attack_share_by_class_pct"]["probe"], "75.9"),
    ("OVS DDoS/brute zero attack windows", C["ovs|ddos"]["attack"] == 0 and C["ovs|brute"]["attack"] == 0,
     "OVS DDoS and OVS brute-force contribute no attack windows"),
    ("Metasp attack windows", sum(C[k]["attack"] for k in MSP) == 2128, "2128 attack windows"),
    ("Metasp probe attack windows", C["metasploitable|probe"]["attack"] == 1922, "1922 (90\\%) of them probe windows"),
    ("OVS attack windows and classes",
     sum(C[k]["attack"] for k in OVSC) == 461 and (C["ovs|botnet"]["attack"], C["ovs|dos"]["attack"],
                                                   C["ovs|probe"]["attack"], C["ovs|web"]["attack"]) == (83, 323, 43, 12),
     "461 OVS attack windows (botnet 83, DoS 323, probe 43, web 12)"),
    ("brute/exploit/web attack windows",
     (C["metasploitable|brute"]["attack"], C["metasploitable|exploit"]["attack"], C["ovs|web"]["attack"]) == (6, 12, 12),
     "6, 12 and 12 attack windows"),
    ("attack-free kept in attack sessions",
     di["within_attack_sessions"]["attack_free_kept_nonempty"] + di["within_attack_sessions"]["attack_free_kept_empty"] == 2178,
     "2178 attack-free windows"),
    ("attack-free empty", di["within_attack_sessions"]["attack_free_kept_empty"] == 1858, "1858 are empty"),
    ("attack-free nonempty without IP",
     (di["within_attack_sessions"]["attack_free_kept_nonempty"],
      di["within_attack_sessions"]["attack_free_kept_nonempty"] - di["within_attack_sessions"]["attack_free_nonempty_with_ip_packetin"]) == (320, 317),
     "of the remaining 320, 317 contain no IP PacketIn"),
    # flow-table priorities and zero-FlowMod captures
    ("ipv4 punt priority 5", fta["priority_by_kind"]["eth_type_0x800"] == {"5": 20116}, "all 20116 observations have priority 5"),
    ("mac-pair priority 10", fta["priority_by_kind"]["mac_pair"] == {"10": 24437}, "all 24437 observations at priority 10"),
    ("arp/lldp/bddp priority 40000",
     all(fta["priority_by_kind"][k] == {"40000": 20116} for k in ("eth_type_0x806", "eth_type_0x88cc", "eth_type_0x8942")),
     "priority 40000"),
    ("zero-FlowMod captures", len(ZERO_FM), "five captures contain none"),
    ("zero-FlowMod captures MAC-pair range", (min(ZERO_FM_MAC), max(ZERO_FM_MAC)) == (4, 73), "4--73 observations per capture"),
    # host-identity baseline (session_identity_baseline.json, Table tab:identity)
    ("identity table R1 all", True, ROW(sb["R1_attacker_only_ip_memory"])),
    ("identity table R2 all", True, ROW(sb["R2_any_attack_ip"])),
    ("identity table MLP all", True, ROW(V4["mlp_all"])),
    ("identity table R1 within", True, ROW(sb["R1_within_attack_nonempty"])),
    ("identity table R2 within", True, ROW(sb["R2_within_attack_nonempty"])),
    ("identity table MLP within", True, ROW(V4["mlp_all_within_attack_nonempty"])),
    ("identity text R1 bacc", f"{SB('R1_attacker_only_ip_memory', 'bacc'):.3f}" == "0.734", "balanced accuracy of 0.734"),
    ("identity text R1 recall", f"{SB('R1_attacker_only_ip_memory', 'recall'):.3f}" == "0.472", "recall limited to 0.472"),
    ("identity text R2 bacc", f"{SB('R2_any_attack_ip', 'bacc'):.3f}" == "0.680", "R2 (0.680)"),
    ("identity text R2 within", f"{SB('R2_within_attack_nonempty', 'bacc'):.3f}" == "0.994", "near-perfect (0.994)"),
    ("paper2 proxy random acc", f"{RP['paper2']['mlp_binary|random']['acc']['mean']:.4f}\\pm{RP['paper2']['mlp_binary|random']['acc']['ci95']:.4f}" == "0.9994\\pm0.0001", "0.9994\\pm0.0001 accuracy under a random split"),
    ("paper2 proxy grouped acc", f"{RP['paper2']['mlp_binary|grouped']['acc']['mean']:.3f}\\pm{RP['paper2']['mlp_binary|grouped']['acc']['ci95']:.3f}" == "0.820\\pm0.202", "0.820\\pm0.202 under held-out source hosts"),
    ("paper2 proxy per-seed", ", ".join(f"{x:.2f}" for x in RP['paper2']['mlp_binary|grouped']['acc']['per_seed']) == "0.68, 0.71, 1.00, 0.71, 0.99", "per-seed: 0.68, 0.71, 1.00, 0.71, 0.99"),
    ("paper2 proxy macro-F1", f"{RP['paper2']['mlp_binary|grouped']['macro_f1']['mean']:.3f}\\pm{RP['paper2']['mlp_binary|grouped']['macro_f1']['ci95']:.3f}" == "0.706\\pm0.299", "macro-F1 0.706\\pm0.299"),
    ("host-side baseline feature count", hs["features"] == 78, "78 numeric features including the two port numbers"),
    ("identity text MLP margin", round(V4["mlp_all"]["bacc"]["mean"] - SB("R1_attacker_only_ip_memory", "bacc"), 2) == 0.21,
     "exceeds R1 by 0.21"),
]
WORDS = {"nine": 9, "ten": 10, "three": 3, "none": 0, "five": 5}
bad = 0
for name, val, quoted in checks:
    num = WORDS.get(quoted.split()[0], quoted)  # quoted word -> number it stands for
    ok = (val is True or str(val) == str(num)) and quoted in tex
    bad += not ok
    print(("OK  " if ok else "FAIL"), name, "json=%s paper=%s" % (val, quoted))
sys.exit(1 if bad else 0)
