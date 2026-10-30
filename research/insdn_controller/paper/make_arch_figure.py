"""Generate publication-quality architecture and evaluation workflow figure for the journal paper."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

fig, ax = plt.subplots(figsize=(7.1, 3.8), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 52)
ax.axis("off")

# Colors
C_BG_ERR = "#fdf2f2"
C_BORDER_ERR = "#d9534f"
C_BG_REAL = "#f0f7f6"
C_BORDER_REAL = "#0f9d8a"
C_BOX_GRAY = "#f8f9fa"
C_TEXT = "#212529"
C_MUTED = "#555555"

def rounded_box(x, y, w, h, bg, border, lw=1.2, r=1.5):
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.2,rounding_size={r}",
                                  facecolor=bg, edgecolor=border, linewidth=lw)
    ax.add_patch(rect)

def arrow(x1, y1, x2, y2, color="#333333", lw=1.2, ls="-"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, mutation_scale=10))

# ----------------- SECTION A: The Conventional Benchmark Paradigm (Flawed) -----------------
rounded_box(1, 28, 98, 22.5, "#fafafa", "#cccccc", lw=1.0)
ax.text(3, 48.5, "(a) Conventional Benchmark Evaluation Paradigm (Offline Host-Tap Disconnect)", 
        fontsize=8.5, fontweight="bold", color="#8b0000")

# Host Tap
rounded_box(3, 31, 20, 15, C_BG_ERR, C_BORDER_ERR)
ax.text(13, 43, "End-Host Data Plane", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(13, 39.5, "Network Tap at Host VM\n(Complete bidirectional packet\nstream captured at socket)", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(13, 33, "Ground Truth: 343k flows", ha="center", fontsize=6, style="italic", color="#777777")

arrow(23.5, 38.5, 27.5, 38.5, color=C_BORDER_ERR)

# CICFlowMeter Extraction
rounded_box(28, 31, 22, 15, "#fff8e7", "#e69f00")
ax.text(39, 43, "Offline Feature Extractor", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(39, 39, "(e.g., CICFlowMeter)\n80+ statistical flow metrics:\n- Inter-arrival times (IAT)\n- Forward/backward lengths\n- TCP flag statistics", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(39, 32.5, "Unobservable at Controller", ha="center", fontsize=6, fontweight="bold", color="#c0392b")

arrow(50.5, 38.5, 54.5, 38.5, color="#e69f00")

# Flawed Train/Test Split
rounded_box(55, 31, 20, 15, C_BG_ERR, C_BORDER_ERR)
ax.text(65, 43, "Evaluation Protocol", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(65, 39, "Random 70:30 Flow Split\n- 48.7% test rows duplicate train\n- Same hosts in train & test\n- Non-disjoint sessions", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(65, 32.5, "Severe Data Leakage", ha="center", fontsize=6, fontweight="bold", color="#c0392b")

arrow(75.5, 38.5, 79.5, 38.5, color=C_BORDER_ERR)

# Illusion Result
rounded_box(80, 31, 17, 15, "#fbeeed", C_BORDER_ERR, lw=1.5)
ax.text(88.5, 43, "Reported Metric", ha="center", fontsize=7.5, fontweight="bold", color="#900")
ax.text(88.5, 38.5, "Accuracy: 99.98%\nBAcc: 0.9998\nCohen's \u03ba: 0.9998", 
        ha="center", fontsize=7, fontweight="bold", color="#900")
ax.text(88.5, 33, "Illusory Generalization\n(Shortcut Learning)", ha="center", fontsize=6, style="italic", color="#777777")


# ----------------- SECTION B: Real SDN Telemetry & Rigorous Methodology (This Work) -----------------
rounded_box(1, 1, 98, 25, "#fafafa", "#cccccc", lw=1.0)
ax.text(3, 23.8, "(b) Actual SDN Observability & Leakage-Controlled Methodology (This Study)", 
        fontsize=8.5, fontweight="bold", color="#005544")

# SDN Control Channel
rounded_box(3, 3.5, 23, 18.5, C_BG_REAL, C_BORDER_REAL)
ax.text(14.5, 19.5, "SDN Control Channel", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(14.5, 16.5, "OpenFlow 1.3 Telemetry Stream:", ha="center", fontsize=6.5, fontweight="bold", color="#006655")
ax.text(14.5, 11.5, "- PacketIn: table misses\n  (dense stream: 0.68-1.29 / pkt)\n- Multipart FlowStats replies\n  (coarse MAC-pair counters)\n- 0 FlowMods match 5-tuple", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(14.5, 5, "44 ONOS Captures Decoded", ha="center", fontsize=6, style="italic", color="#006655")

arrow(26.5, 12.5, 30.5, 12.5, color=C_BORDER_REAL)

# Featurization
rounded_box(31, 3.5, 20, 18.5, C_BG_REAL, C_BORDER_REAL)
ax.text(41, 19.5, "Window Featurizer", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(41, 16.5, "Observable Features ($W{=}1s, 5s$):", ha="center", fontsize=6.2, fontweight="bold", color=C_TEXT)
ax.text(41, 11.5, "- 22 Control-plane features\n- Header fractions (TCP/UDP/SYN)\n- Port & IP entropies\n- Message arrival counts\n- 4-window temporal lag", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(41, 5, "Strict Ground-Truth Labels", ha="center", fontsize=6, style="italic", color="#006655")

arrow(51.5, 12.5, 55.5, 12.5, color=C_BORDER_REAL)

# Rigorous Controls
rounded_box(56, 3.5, 22, 18.5, "#eef5fc", "#2a6f97")
ax.text(67, 19.5, "Methodological Controls", ha="center", fontsize=7.5, fontweight="bold", color=C_TEXT)
ax.text(67, 16.5, "Topology & Leakage Audits:", ha="center", fontsize=6.2, fontweight="bold", color="#1a4f77")
ax.text(67, 11.5, "- Held-Out Source Hosts\n- Leave-One-Host-Out (LOHO)\n- Complete Deduplication\n- Class-Coverage Safeguards\n- Forwarding Mode Sensitivity", 
        ha="center", fontsize=6.2, color=C_MUTED)
ax.text(67, 5, "Realistic Attack Stress-Test", ha="center", fontsize=6, style="italic", color="#1a4f77")

arrow(78.5, 12.5, 82.5, 12.5, color="#2a6f97")

# Honest Outcome
rounded_box(83, 3.5, 15, 18.5, "#e8f5e9", "#2e7d32", lw=1.5)
ax.text(90.5, 19.5, "Realistic Audit", ha="center", fontsize=7.5, fontweight="bold", color="#1b5e20")
ax.text(90.5, 15, "Held-out Hosts:\nBAcc drops to\n0.907 \u00b1 0.085\n(Worst: 0.66)", 
        ha="center", fontsize=6.5, fontweight="bold", color="#1b5e20")
ax.text(90.5, 8.5, "Unseen Attacker:\nRecall = 51.6%\nBenign FPR = 37.9%", 
        ha="center", fontsize=6.2, fontweight="bold", color="#c0392b")
ax.text(90.5, 4.8, "Honest Generalization", ha="center", fontsize=5.8, style="italic", color="#555555")

plt.tight_layout()
fig.savefig(OUT_DIR / "fig_architecture.pdf", bbox_inches="tight")
print("fig_architecture.pdf successfully generated at", OUT_DIR / "fig_architecture.pdf")
