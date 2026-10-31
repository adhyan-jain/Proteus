"""Paper figures from results/*.json (no hand-copied numbers). Usage: make_figures.py <out_dir>"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

R = Path(__file__).resolve().parent.parent / "results"
OUT = Path(sys.argv[1])
J = lambda f: json.loads((R / f).read_text().replace("NaN", "null"))  # noqa: E731
TEAL, AMBER, RED, GRAY, PURPLE = "#0f9d8a", "#e69f00", "#d55e5e", "#7a8699", "#7e6bc9"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "STIXGeneral", "serif"],
    "mathtext.fontset": "stix",
    "font.size": 8,
    "axes.labelsize": 8.5,
    "axes.titlesize": 9,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 6.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "figure.dpi": 300,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)


# 1 forwarding: PacketIns per run, log scale, one switch vs three
one, l3 = J("live_modes_v4_one10.json")["summary"], J("live_modes_v4_linear3.json")["summary"]
modes = [("mac", "MAC-pair"), ("fivetuple_short", "5-tuple\n2 s idle"), ("fivetuple", "5-tuple\n10 s idle")]
fig, ax = plt.subplots(figsize=(3.45, 2.3))
x = np.arange(len(modes))
for k, (d, lab, col) in enumerate([(one, "1 switch", TEAL), (l3, "3-switch chain", AMBER)]):
    m = [d[m_]["packet_in_tcp"]["mean"] for m_, _ in modes]
    e = [d[m_]["packet_in_tcp"]["ci95"] for m_, _ in modes]
    b = ax.bar(x + (k - 0.5) * 0.38, m, 0.36, yerr=e, color=col, label=lab,
               error_kw=dict(capsize=2.5, elinewidth=0.8, ecolor="#222222"))
    for xi, v, err in zip(x + (k - 0.5) * 0.38, m, e):
        y_pos = (v + err) * 1.55 if v > 100 else (v + err) * 1.45
        ax.text(xi, y_pos, f"{v:,.0f}", ha="center", va="bottom", fontsize=6.2)
ax.set_yscale("log")
ax.set_ylim(1, 2.5e5)
ax.set_xticks(x, [l for _, l in modes])
ax.set_ylabel("TCP PacketIns per run")
ax.legend(frameon=False, loc="upper left", fontsize=7)
save(fig, "fig_forwarding.pdf")

# 2 scores vs trivial rule
w1, w5 = J("v4_strict_W1.json")["A_grouped_cv"], J("v4_strict_W5_xgb.json")["A_grouped_cv"]
rc = J("review_checks.json")
labs = ["Rate thr.", "Entropy thr.", "Logistic", "MLP (4-win)", "XGBoost (5 s)", "Trivial rule\n(any IP)"]
rows = [("Rate thr.", "thr_packet_in_rate"), ("Entropy thr.", "thr_src_ip_entropy"),
        ("Logistic", "linear_all_history"), ("MLP (4-win)", "mlp_all")]
v1 = [w1[k]["bacc"]["mean"] for _, k in rows] + [np.nan, rc["within_session_W1_strict"]["any_ip_packet_in"]["bacc_pooled"]]
v5 = [w5[k]["bacc"]["mean"] for _, k in rows] + [w5["xgb_all_history"]["bacc"]["mean"], rc["within_session_W5_strict"]["any_ip_packet_in"]["bacc_pooled"]]

fig, ax = plt.subplots(figsize=(3.45, 2.5))
ax.grid(axis="y", linestyle=":", alpha=0.4, color="#999999", zorder=0)
x = np.arange(len(labs))
ax.bar(x - 0.18, v1, 0.34, color=TEAL, label="1 s windows", zorder=2)
ax.bar(x + 0.18, v5, 0.34, color=AMBER, label="5 s windows", zorder=2)
# Missing XGBoost 1s indicator
ax.text(4 - 0.18, 0.43, "—", ha="center", va="bottom", fontsize=7.5, color="#888888")
# Trivial rule separator
ax.axvline(4.5, color="#bbbbbb", linestyle=":", lw=0.9, zorder=3)
ax.set_xticks(x, labs, rotation=25, ha="right", fontsize=6.8)
ax.set_ylim(0.4, 1.05)
ax.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
ax.set_ylabel("Balanced accuracy")
ax.legend(frameon=True, facecolor="white", edgecolor="#e0e0e0", framealpha=0.95, loc="upper left", fontsize=6.8)
save(fig, "fig_scores.pdf")

# 3 split protocol: two datasets, four protocols (results/protocol_audit_*.json)
audit = [("InSDN", J("protocol_audit_insdn.json")), ("CICIDS2017", J("protocol_audit_cicids2017.json"))]
protos = [("A_random_flow_split", "Random flow (Prot. A)", AMBER),
          ("B_source_ip_grouped_split", "Source-IP-disjoint (Prot. B)", RED),
          ("C_time_ordered_split", "Time-ordered (Prot. C)", TEAL),
          ("D_identifier_only_random_split", "Identifiers only (Prot. D)", PURPLE)]

fig, ax = plt.subplots(figsize=(3.45, 2.5))
ax.grid(axis="y", linestyle=":", alpha=0.4, color="#999999", zorder=0)
w = 0.20
for j, (key, lab, col) in enumerate(protos):
    xs = np.arange(len(audit)) + (j - 1.5) * w
    vals = [d[key]["mean"] for _, d in audit]
    ci95s = [d[key].get("ci95", 0.0) if key.startswith("B_") else 0.0 for _, d in audit]
    ax.bar(xs, vals, w * 0.88, color=col, label=lab, yerr=ci95s if any(ci95s) else None,
           error_kw=dict(capsize=3.0, elinewidth=0.9, ecolor="#222222"), zorder=2)
    if key.startswith("B_"):
        for x_i, (_, d) in zip(xs, audit):
            ps = d[key]["per_seed"]
            jitter = np.linspace(-0.025, 0.025, len(ps))
            ax.scatter(np.full(len(ps), x_i) + jitter, ps, s=9, color="#111111", alpha=0.6, zorder=4,
                       label="Individual seeds" if x_i == xs[0] else None)

ax.set_xticks(range(len(audit)), [n for n, _ in audit], fontsize=8.5)
ax.set_ylim(0.4, 1.05)
ax.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
ax.set_ylabel("Balanced accuracy")
handles, labels = ax.get_legend_handles_labels()
order = [0, 1, 3, 2, 4]
ax.legend([handles[i] for i in order], [labels[i] for i in order],
          frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3,
          fontsize=5.8, columnspacing=0.6, handletextpad=0.3)
save(fig, "fig_split.pdf")

# 4 PacketIns per target packet per scenario
gap = J("gap_attack_v2.json")
sc_names = {
    "Metsplotable-2_Group/metasploitable-2_brute-force-attack": "MS2 Brute",
    "Metsplotable-2_Group/metasploitable-2_ddos": "MS2 DDoS",
    "Metsplotable-2_Group/metasploitable-2_dos": "MS2 DoS",
    "Metsplotable-2_Group/metasploitable-2_exploit": "MS2 Exploit",
    "Metsplotable-2_Group/metasploitable-2_probe": "MS2 Probe",
    "OVS_Group/Botnet": "OVS Botnet",
    "OVS_Group/DDoS": "OVS DDoS",
    "OVS_Group/Probe": "OVS Probe",
    "OVS_Group/brute-force-attack": "OVS Brute",
    "OVS_Group/dos/Application_DoS": "OVS App DoS",
    "OVS_Group/dos/Network_DoS": "OVS Net DoS",
    "OVS_Group/web_attack": "OVS Web",
}
items = [(sc_names[k], v["packet_in_per_target_packet"]) for k, v in gap.items() if k in sc_names]
fig, ax = plt.subplots(figsize=(3.45, 2.3))
x_idx = range(len(items))
ax.bar(x_idx, [v for _, v in items], color=AMBER, edgecolor="#b37400", linewidth=0.5)
ax.axhline(1, color=GRAY, lw=0.8, ls="--")
ax.text(11.2, 1.15, "1:1 ratio", fontsize=6.2, color="#555555", style="italic", ha="right",
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
ax.set_xticks(x_idx, [n for n, _ in items], rotation=38, ha="right", fontsize=6.2)
ax.set_yscale("log")
ax.set_ylim(0.04, 35)
ax.set_ylabel("PacketIns per target packet")
save(fig, "fig_packetin_ratio.pdf")
print("figures written to", OUT)
