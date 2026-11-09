"""Generate updated LaTeX tables from newly verified experimental results:
1. table_weighting.tex (Host-weighting comparison: unweighted, sqrt, inv-freq, clipped, class-cond)
2. table_multiprotocol.tex (Multi-protocol splitting: Random, Src-IP, Dst-IP, Pair, Non-spoofed)
3. table_combinatorial_50seeds.tex (50-seed combinatorial audit & regime breakdown)
"""
import json
from pathlib import Path

RESULTS_DIR = Path("research/insdn_controller/results")
PAPER_DIR = Path("research/insdn_controller/paper")

def generate_weighting_table():
    with open(RESULTS_DIR / "host_weighting_audit.json") as fp:
        data = json.load(fp)

    summary = data["summary"]
    rows = [
        ("Unweighted ERM (Standard)", "unweighted", "110,799 : 1", "0.907", "0.085", "0.660", "0.832", "0.188"),
        ("Square-root attenuation ($1/\\sqrt{N_h}$)", "sqrt_attenuation", "333 : 1", "0.931", "0.064", "0.730", "0.835", "0.149"),
        ("Pure inverse-frequency ($1/N_h$)", "inv_freq", "1 : 1", "0.835", "0.158", "0.337", "0.706", "0.193"),
        ("Clipped inverse-frequency ($99\\%$ cap)", "inv_freq_clipped", "1 : 1 (reg.)", "0.835", "0.158", "0.337", "0.706", "0.193"),
        ("Class-conditional ($1/N_{h,c}$)", "class_conditional_inv_freq", "Class-relative", "0.826", "0.158", "0.342", "0.685", "0.202"),
    ]

    tex = [
        "\\begin{table}[t]",
        "\\caption{Comparison of sample-weighting strategies under source-IP-disjoint evaluation (InSDN Protocol~B, 10 seeds, mean{\\scriptsize$\\pm$}95\\% CI). Ratio = total sample weight of primary attacker host relative to a single-flow host. Paired difference for square-root attenuation vs.\\ ERM: $\\bar{\\Delta} = +0.0238\\pm 0.0415$ ($p = 0.2267$).}",
        "\\label{tab:weighting_audit}",
        "\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}",
        "\\resizebox{\\columnwidth}{!}{%",
        "\\begin{tabular}{lcccc}",
        "\\toprule",
        "Weighting Strategy & Sample Weight Ratio & BAcc & Worst Seed & Macro-F1 \\\\",
        "\\midrule",
    ]

    for label, key, ratio, b_mean, b_ci, b_min, f_mean, f_ci in rows:
        d = summary[key]
        tex.append(f"{label} & {ratio} & {d['bacc']['mean']:.3f}{{\\scriptsize$\\pm${d['bacc']['ci95']:.3f}}} & {d['bacc']['min']:.3f} & {d['macro_f1']['mean']:.3f}{{\\scriptsize$\\pm${d['macro_f1']['ci95']:.3f}}} \\\\")

    tex.extend([
        "\\bottomrule",
        "\\end{tabular}%",
        "}",
        "\\end{table}",
        "",
    ])

    out_file = PAPER_DIR / "table_weighting.tex"
    out_file.write_text("\n".join(tex))
    print(f"Generated {out_file}")

def generate_multiprotocol_table():
    with open(RESULTS_DIR / "multiprotocol_split_audit.json") as fp:
        data = json.load(fp)

    summary = data["summary"]
    rows = [
        ("Protocol A: Random flow split", "A_random_flow", "Overlapping", "0.9998", "0.0000", "0.9999", "0.0000"),
        ("Protocol B: Source-IP-disjoint", "B_src_ip_grouped", "Disjoint Src IP", "0.9074", "0.0847", "0.8321", "0.1883"),
        ("Protocol B$_{\\text{dst}}$: Destination-IP-disjoint", "B_dst_ip_grouped", "Disjoint Dst IP", "0.8727", "0.0881", "0.8141", "0.1046"),
        ("Protocol B$_{\\text{pair}}$: (Src, Dst) Pair-disjoint", "B_pair_grouped", "Disjoint (Src, Dst)", "0.9891", "0.0084", "0.9767", "0.0193"),
        ("Protocol B$_{\\text{nospoof}}$: Non-spoofed Source IP", "B_non_spoofed_src_grouped", "Disjoint (No Spoof)", "0.8417", "0.1114", "0.6503", "0.2005"),
    ]

    tex = [
        "\\begin{table}[t]",
        "\\caption{Evaluation-validity audit across network partitioning protocols on InSDN (77 numeric CICFlowMeter features, identifiers excluded, GPU XGBoost, 10 seeds, mean{\\scriptsize$\\pm$}95\\% CI).}",
        "\\label{tab:multiprotocol}",
        "\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}",
        "\\resizebox{\\columnwidth}{!}{%",
        "\\begin{tabular}{lcccc}",
        "\\toprule",
        "Partitioning Protocol & Address Isolation & Balanced Accuracy & Min BAcc & Macro-F1 \\\\",
        "\\midrule",
    ]

    for label, key, isolation, _, _, _, _ in rows:
        d = summary[key]
        tex.append(f"{label} & {isolation} & {d['bacc']['mean']:.4f}{{\\scriptsize$\\pm${d['bacc']['ci95']:.4f}}} & {d['bacc']['min']:.4f} & {d['macro_f1']['mean']:.4f}{{\\scriptsize$\\pm${d['macro_f1']['ci95']:.4f}}} \\\\")

    tex.extend([
        "\\bottomrule",
        "\\end{tabular}%",
        "}",
        "\\end{table}",
        "",
    ])

    out_file = PAPER_DIR / "table_multiprotocol.tex"
    out_file.write_text("\n".join(tex))
    print(f"Generated {out_file}")

def generate_combinatorial_50seeds_table():
    with open(RESULTS_DIR / "combinatorial_audit_50seeds.json") as fp:
        data = json.load(fp)

    reg = data["regime_summary"]
    tex = [
        "\\begin{table}[t]",
        "\\caption{Combinatorial dominant host allocation across 50 Protocol~B seeds on InSDN (GroupShuffleSplit 70:30, $M=122\\,868, k=\\lceil 0.3M \\rceil = 36\\,861$). Correlation between test partition row share and balanced accuracy: $r = -0.7713$ ($p = 5.61 \\times 10^{-11}$).}",
        "\\label{tab:combinatorial_50seeds}",
        "\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}",
        "\\resizebox{\\columnwidth}{!}{%",
        "\\begin{tabular}{lccccc}",
        "\\toprule",
        "Allocation Regime & Seeds ($N$) & Hypergeom. Theory & Empirical Pct & Mean BAcc & BAcc Range \\\\",
        "\\midrule",
        f"Neither primary host withheld & {reg['neither_withheld']['count']} & 49.0\\% & {100*data['empirical_frequencies_50seeds']['neither_withheld']:.1f}\\% & {reg['neither_withheld']['mean']:.4f} & [{reg['neither_withheld']['min']:.4f}, {reg['neither_withheld']['max']:.4f}] \\\\",
        f"Primary attacker withheld only & {reg['att_only_withheld']['count']} & 21.0\\% & {100*data['empirical_frequencies_50seeds']['att_only_withheld']:.1f}\\% & {reg['att_only_withheld']['mean']:.4f} & [{reg['att_only_withheld']['min']:.4f}, {reg['att_only_withheld']['max']:.4f}] \\\\",
        f"Primary benign withheld only & {reg['ben_only_withheld']['count']} & 21.0\\% & {100*data['empirical_frequencies_50seeds']['ben_only_withheld']:.1f}\\% & {reg['ben_only_withheld']['mean']:.4f} & [{reg['ben_only_withheld']['min']:.4f}, {reg['ben_only_withheld']['max']:.4f}] \\\\",
        f"Both primary hosts withheld & {reg['both_withheld']['count']} & 9.0\\% & {100*data['empirical_frequencies_50seeds']['both_withheld']:.1f}\\% & {reg['both_withheld']['mean']:.4f} & [{reg['both_withheld']['min']:.4f}, {reg['both_withheld']['max']:.4f}] \\\\",
        "\\midrule",
        f"\\textbf{{Overall Population (50 Seeds)}} & \\textbf{{50}} & \\textbf{{100.0\\%}} & \\textbf{{100.0\\%}} & \\textbf{{{data['overall_bacc']['mean']:.4f}}}{{\\scriptsize$\\pm${data['overall_bacc']['ci95']:.4f}}} & \\textbf{{[{data['overall_bacc']['min']:.4f}, {data['overall_bacc']['max']:.4f}]}} \\\\",
        "\\bottomrule",
        "\\end{tabular}%",
        "}",
        "\\end{table}",
        "",
    ]

    out_file = PAPER_DIR / "table_combinatorial_50seeds.tex"
    out_file.write_text("\n".join(tex))
    print(f"Generated {out_file}")

if __name__ == "__main__":
    generate_weighting_table()
    generate_multiprotocol_table()
    generate_combinatorial_50seeds_table()
