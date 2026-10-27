"""Generate paper/tables.tex from the stored result files (no hand-copied numbers).

Usage: make_tables.py <results_json> <gap_json> <feats_meta_json> <out_tex>
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

R = json.loads(Path(sys.argv[1]).read_text())
RC = json.loads(Path(sys.argv[5]).read_text()) if len(sys.argv) > 5 else None
G = json.loads(Path(sys.argv[2]).read_text())
M = json.loads(Path(sys.argv[3]).read_text())
out = []


def pm(d, nd=3):
    return f"{d['mean']:.{nd}f}{{\\scriptsize$\\pm${d['ci95']:.{nd}f}}}"


def v(d, nd=3):
    return f"{d['mean']:.{nd}f}"


def table(label, caption, colspec, header, rows, size="\\footnotesize\\setlength{\\tabcolsep}{3pt}"):
    out.append(f"\\begin{{table}}[t]\n\\caption{{{caption}}}\n\\label{{{label}}}\n\\centering{size}\n"
               f"\\begin{{tabular}}{{{colspec}}}\n\\toprule\n{header} \\\\\n\\midrule")
    for r in rows:
        out.append(r + " \\\\" if r != "\\midrule" else r)
    out.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n")


# ---- inventory
agg = collections.defaultdict(collections.Counter)
for m in M.values():
    a = agg[m["label"]]
    a["caps"] += 1
    a["windows"] += m["windows_1s"]
    a["pin"] += m["packet_in"]
inv = R["inventory"]
order = ["normal", "dos", "ddos", "probe", "brute", "exploit", "web", "botnet"]
names = {"normal": "Normal", "dos": "DoS", "ddos": "DDoS", "probe": "Probe", "brute": "Brute force",
         "exploit": "Exploit", "web": "Web", "botnet": "Botnet"}
rows = [f"{names[c]} & {inv[c]['captures']} & {inv[c]['windows']:,} & {inv[c]['windows_kept']:,} & "
        f"{inv[c]['attack_windows']:,} & {agg[c]['pin']:,}" for c in order]
table("tab:inventory", "Controller captures (1\\,s windows). Under strict labels, ambiguous windows of attack "
      "captures are excluded (``kept'').", "lrrrrr", "Class & Captures & Windows & Kept & Attack win. & PacketIns", rows)

# ---- gap
sc = {"Metsplotable-2_Group/metasploitable-2_brute-force-attack": ("Metasp.", "Brute force"),
      "Metsplotable-2_Group/metasploitable-2_ddos": ("Metasp.", "DDoS"),
      "Metsplotable-2_Group/metasploitable-2_dos": ("Metasp.", "DoS"),
      "Metsplotable-2_Group/metasploitable-2_exploit": ("Metasp.", "Exploit"),
      "Metsplotable-2_Group/metasploitable-2_probe": ("Metasp.", "Probe"),
      "OVS_Group/Botnet": ("OVS", "Botnet"), "OVS_Group/DDoS": ("OVS", "DDoS"), "OVS_Group/Probe": ("OVS", "Probe"),
      "OVS_Group/brute-force-attack": ("OVS", "Brute force"), "OVS_Group/dos/Application_DoS": ("OVS", "App.\\ DoS"),
      "OVS_Group/dos/Network_DoS": ("OVS", "Net.\\ DoS"), "OVS_Group/web_attack": ("OVS", "Web")}
rows = []
for k, (grp, nm) in sc.items():
    g = G[k]
    rows.append(f"{grp} & {nm} & {g['target']['packets']:,} & {g['target']['five_tuples']:,} & "
                f"{g['controller']['packet_in']:,} & {g['packet_in_per_target_packet']:.2f}")
table("tab:gap", "Target-side traffic vs.\\ controller observations per scenario (ratio = PacketIns per target packet).",
      "llrrrr", "Group & Scenario & Target pkts & 5-tuples & PacketIns & Ratio", rows, "\\footnotesize")

# ---- main CV table
A = R["A_grouped_cv"]
spec = [("MLP, all features", "mlp_all"), ("MLP, PacketIn features only", "mlp_packet_in_only"),
        ("Logistic regression (history)", "linear_all_history"), ("MLP, single window", "mlp_all_single_window"),
        ("Thr.\\ source-IP entropy", "thr_src_ip_entropy"), ("Thr.\\ dst-port entropy", "thr_dport_entropy"),
        ("MLP, flow-stats features only", "mlp_stats_only"), ("Thr.\\ PacketIn burst", "thr_packet_in_burst"),
        ("Thr.\\ PacketIn rate", "thr_packet_in_rate")]
rows = [f"{n} & {pm(A[k]['bacc'])} & {v(A[k]['recall'])} & {v(A[k]['fpr'])}" for n, k in spec]
rows.append("\\midrule")
w = A["mlp_all_within_attack_nonempty"]
rows.append(f"MLP, within attack sessions & {pm(w['bacc'])} & {v(w['recall'])} & {v(w['fpr'])}")
mc = A["mlp_all_within_attack_nonempty_macro_capture"]["bacc"]
rows.append(f"\\quad macro-averaged over captures & {pm(mc)} & -- & --")
if RC is not None:
    ti = RC["within_session_W1_strict"]["any_ip_packet_in"]
    rows.append(f"Trivial: ``any IP PacketIn'' (same windows) & {ti['bacc_pooled']:.3f} & -- & --")
    rows.append(f"\\quad macro over captures & {ti['bacc_macro_captures']:.3f} & -- & --")
table("tab:cv", "Unseen captures, grouped 5-fold CV, $W{=}1$\\,s, strict labels, 10 seeds (mean{\\scriptsize$\\pm$}95\\% CI over seeds).",
      "lccc", "Method & BAcc & Recall & FPR", rows)

# ---- cluster bootstrap
B = R["A_capture_cluster_bootstrap"]
bn = [("MLP, all features", "mlp_all"), ("Logistic regression", "linear_all_history"),
      ("MLP, single window", "mlp_all_single_window"), ("Thr.\\ source-IP entropy", "thr_src_ip_entropy"),
      ("Thr.\\ dst-port entropy", "thr_dport_entropy"), ("Thr.\\ PacketIn rate", "thr_packet_in_rate")]
rows = [f"{n} & {B[k]['bacc_pooled']:.3f} & [{B[k]['ci95_lo']:.3f}, {B[k]['ci95_hi']:.3f}]" for n, k in bn]
table("tab:boot", "Pooled window-count BAcc with a capture-level cluster bootstrap (2000 resamples, stratified by class).",
      "lcc", "Method & Pooled BAcc & 95\\% CI", rows)

# ---- family holdout
F = R["B_leave_one_attack_family_out"]
fam = [("Flood (DoS+DDoS)", "flood"), ("Probe", "probe"), ("Web", "web"), ("Brute force", "brute"),
       ("Exploit", "exploit"), ("Botnet", "botnet")]
rows = []
for n, k in fam:
    d = F[k]
    best = max(d[x]["bacc"]["mean"] for x in d if x.startswith("thr"))
    rows.append(f"{n} & {pm(d['mlp_all']['bacc'])} & {v(d['linear_all_history']['bacc'])} & {best:.3f}")
table("tab:family", "Withheld attack family (BAcc, $W{=}1$\\,s, strict labels). ``Best thr.'': best of four thresholds, chosen per family.",
      "lccc", "Withheld family & MLP & Logistic & Best thr.", rows)

# ---- cross deployment
C = R["C_cross_deployment"]
rows = []
for k, nm in (("metasploitable->ovs", "Metasploitable-2 $\\rightarrow$ OVS"), ("ovs->metasploitable", "OVS $\\rightarrow$ Metasploitable-2")):
    d = C[k]
    best = max(d[x]["bacc"]["mean"] for x in d if x.startswith("thr"))
    rows.append(f"{nm} & {pm(d['mlp_all']['bacc'])} & {v(d['linear_all_history']['bacc'])} & {best:.3f}")
table("tab:cross", "Cross-deployment transfer (BAcc, strict labels).", "lccc", "Train $\\rightarrow$ test & MLP & Logistic & Best thr.", rows)

# ---- confound
D = R["D_session_confound_probe"]
rows = [f"All windows (D1) & {pm(D['D1_all_windows']['bacc'])} & {v(D['D1_all_windows_majority_baseline']['bacc'])}",
        f"Attack-free windows only (D2) & {pm(D['D2_attack_free_windows_only']['bacc'])} & {v(D['D2_attack_free_windows_only_majority_baseline']['bacc'])}"]
table("tab:confound", "Session probe: predicting benign vs.\\ attack \\emph{session} from PacketIn features after removing attack-matched PacketIns (${\\ge}5$ remaining per window). The residual can still contain unlisted attack traffic (D1: 424 of 518 attack-session windows contain unmatched-IP PacketIns), and D2 rests on 6 windows from 2 captures.",
      "lcc", "Variant & BAcc & Majority", rows)

Path(sys.argv[4]).write_text("\n".join(out))
print("wrote", sys.argv[4], len(out), "blocks")
