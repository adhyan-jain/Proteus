"""LaTeX table of strictly labelled windows per deployment and class, from results/deployment_inventory.json.

Usage: python make_deployment_table.py <deployment_inventory.json> <out.tex>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEP = {"metasploitable": "Metasp.", "ovs": "OVS", "normal": "Normal"}
CLS = {"normal": "Normal", "dos": "DoS", "ddos": "DDoS", "probe": "Probe", "brute": "Brute force",
       "exploit": "Exploit", "web": "Web", "botnet": "Botnet"}
ORDER = ["metasploitable|brute", "metasploitable|ddos", "metasploitable|dos", "metasploitable|exploit",
         "metasploitable|probe", "ovs|botnet", "ovs|brute", "ovs|ddos", "ovs|dos", "ovs|probe", "ovs|web",
         "normal|normal"]


def main():
    d = json.loads(Path(sys.argv[1]).read_text())
    rows = []
    for k in ORDER:
        v = d["cells"][k]
        dep, cls = k.split("|")
        rows.append(f"{DEP[dep]} & {CLS[cls]} & {v['captures']} & {v['windows']:,} & {v['kept']:,} & "
                    f"{v['attack']:,} \\\\")
    tot = d["total_attack_windows"]
    body = "\n".join(rows)
    tex = (
        "\\begin{table}[t]\n"
        "\\caption{Strictly labelled controller windows ($W{=}1$\\,s) per deployment and class. A class with zero attack "
        "windows contributes only attack-free windows: OVS DDoS and OVS brute-force have no CSV-matched flows "
        f"(Section~\\ref{{sec:method}}). Probe supplies {d['attack_share_by_class_pct']['probe']}\\% of the "
        f"{tot:,} pooled attack windows.}}\n"
        "\\label{tab:deployment}\n"
        "\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabular}{llrrrr}\n\\toprule\n"
        "Deployment & Class & Captures & Windows & Kept & Attack win. \\\\\n\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")
    Path(sys.argv[2]).write_text(tex)
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(recon_table(json.loads(Path(sys.argv[3]).read_text())))


def recon_table(r):
    """Reconstruction-from-PacketIn quality per scenario (packetin_reconstruction.json)."""
    names = [("OVS_DDoS", "OVS DDoS"), ("OVS_Probe", "OVS Probe"), ("OVS_Web", "OVS Web"), ("MS2_DoS", "MS2 DoS"),
             ("MS2_Probe", "MS2 Probe"), ("Normal_1", "Normal (1 of 11)")]
    rows = []
    for key, label in names:
        v = r[key]
        few = v["matching_5tuples"] < 30   # too few matched flows for a correlation to mean anything
        fmt = lambda x: "--" if (x is None or few) else f"{x:.2f}"   # noqa: E731
        rows.append(f"{label} & {v['distinct_reconstructed_flows']:,} & {v['pct_single_packet_flows']:.1f} & "
                    f"{v['matching_5tuples']:,} & {v['matched_share_of_reconstructed_pct']:.1f} & "
                    f"{fmt(v['packet_count_spearman'])} & {fmt(v['packet_sum_ratio_recon_over_csv'])} & "
                    f"{fmt(v['duration_spearman'])} \\\\")
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n"
        "\\caption{Flows reassembled from PacketIns (120\\,s timeout, FIN/RST termination) against the benchmark CSV "
        "for one capture per scenario. Correlations and the packet ratio use only matched 5-tuples and are omitted "
        "(--) below 30 matches. Ratio = reconstructed over host-side packet total.}\n"
        "\\label{tab:recon}\n"
        "\\centering\\footnotesize\\setlength{\\tabcolsep}{2.0pt}\n"
        "\\begin{tabular}{lrrrrrrr}\n\\toprule\n"
        "Scenario & Flows & 1-pkt \\% & Matched & Matched \\% & $\\rho_{\\text{pkt}}$ & Ratio & $\\rho_{\\text{dur}}$ \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n\\end{tabular}\n\\end{table}\n")


if __name__ == "__main__":
    main()
