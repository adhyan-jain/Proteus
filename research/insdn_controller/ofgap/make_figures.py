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
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)


# 1 forwarding: PacketIns per run, log scale, one switch vs three
one, l3 = J("live_modes_v4_one10.json")["summary"], J("live_modes_v4_linear3.json")["summary"]
modes = [("mac", "MAC-pair"), ("fivetuple_short", "Per-flow\n2 s idle"), ("fivetuple", "Per-flow\n10 s idle")]
fig, ax = plt.subplots(figsize=(3.4, 2.3))
x = np.arange(len(modes))
for k, (d, lab, col) in enumerate([(one, "1 switch", TEAL), (l3, "3-switch chain", AMBER)]):
    m = [d[m_]["packet_in_tcp"]["mean"] for m_, _ in modes]
    e = [d[m_]["packet_in_tcp"]["ci95"] for m_, _ in modes]
    b = ax.bar(x + (k - 0.5) * 0.38, m, 0.36, yerr=e, color=col, label=lab, capsize=2)
    for xi, v in zip(x + (k - 0.5) * 0.38, m):
        ax.text(xi, v * 1.15, f"{v:,.0f}", ha="center", fontsize=6.5)
ax.set_yscale("log")
ax.set_ylim(1, 5e4)
ax.set_xticks(x, [l for _, l in modes])
ax.set_ylabel("TCP PacketIns per run")
ax.legend(frameon=False, loc="upper left")
save(fig, "fig_forwarding.pdf")

# 2 scores vs trivial rule
w1, w5 = J("v4_strict_W1.json")["A_grouped_cv"], J("v4_strict_W5_xgb.json")["A_grouped_cv"]
rc = J("review_checks.json")
rows = [("PacketIn-rate\nthreshold", "thr_packet_in_rate"), ("IP-entropy\nthreshold", "thr_src_ip_entropy"), ("Logistic", "linear_all_history"), ("MLP", "mlp_all")]
fig, ax = plt.subplots(figsize=(3.4, 2.3))
labs = [r[0] for r in rows] + ["XGBoost", "Trivial rule\n(any IP PacketIn)"]
v1 = [w1[k]["bacc"]["mean"] for _, k in rows] + [np.nan, rc["within_session_W1_strict"]["any_ip_packet_in"]["bacc_pooled"]]
v5 = [w5[k]["bacc"]["mean"] for _, k in rows] + [w5["xgb_all_history"]["bacc"]["mean"], rc["within_session_W5_strict"]["any_ip_packet_in"]["bacc_pooled"]]
x = np.arange(len(labs))
ax.bar(x - 0.19, v1, 0.36, color=TEAL, label="1 s windows")
ax.bar(x + 0.19, v5, 0.36, color=AMBER, label="5 s windows")
ax.bar([x[-1] - 0.19, x[-1] + 0.19], [v1[-1], v5[-1]], 0.36, color=RED)
ax.set_xticks(x, labs, fontsize=6)
ax.set_ylim(0.4, 1.05)
ax.set_ylabel("Balanced accuracy")
ax.legend(frameon=False, loc="lower right", fontsize=6.5)
save(fig, "fig_scores.pdf")

# 3 split protocol: two datasets, four protocols (results/protocol_audit_*.json)
audit = [("InSDN", J("protocol_audit_insdn.json")), ("CICIDS2017", J("protocol_audit_cicids2017.json"))]
protos = [("A_random_flow_split", "Random flow split", AMBER), ("B_source_ip_grouped_split", "Held-out source hosts", RED),
          ("C_time_ordered_split", "Time-ordered per file", TEAL), ("D_identifier_only_random_split", "IPs and ports only", PURPLE)]
fig, ax = plt.subplots(figsize=(3.4, 2.7))
w = 0.2
for j, (key, lab, col) in enumerate(protos):
    xs = np.arange(len(audit)) + (j - 1.5) * w
    vals = [d[key]["mean"] for _, d in audit]
    ax.bar(xs, vals, w * 0.92, color=col, label=lab)
    for x, (_, d), v in zip(xs, audit, vals):
        top = max([v] + (d[key]["per_seed"] if key.startswith("B_") else []))
        ax.text(x, top + 0.012, f"{v:.2f}", ha="center", fontsize=5.5)
    if key.startswith("B_"):
        for x, (_, d) in zip(xs, audit):
            ps = d[key]["per_seed"]
            ax.scatter(np.full(len(ps), x) + np.linspace(-0.04, 0.04, len(ps)), ps, s=4, color="black", zorder=3,
                       label="individual host splits" if x == xs[0] else None)
ax.set_xticks(range(len(audit)), [n for n, _ in audit], fontsize=7)
ax.set_ylim(0.4, 1.08)
ax.set_ylabel("Balanced accuracy")
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=5.5, columnspacing=0.8, handlelength=1.2)
save(fig, "fig_split.pdf")

# 4 PacketIns per target packet per scenario
gap = J("gap_attack_v2.json")
items = [(("MS2" if k.startswith("Mets") else "OVS") + " " + v["label"], v["packet_in_per_target_packet"]) for k, v in gap.items() if v.get("packet_in_per_target_packet") is not None]
fig, ax = plt.subplots(figsize=(3.4, 2.3))
ax.bar(range(len(items)), [v for _, v in items], color=AMBER)
ax.axhline(1, color=GRAY, lw=0.8, ls="--")
ax.set_xticks(range(len(items)), [n for n, _ in items], rotation=60, ha="right", fontsize=6)
ax.set_yscale("log")
ax.set_ylabel("PacketIns per target packet")
save(fig, "fig_packetin_ratio.pdf")
print("figures written to", OUT)
