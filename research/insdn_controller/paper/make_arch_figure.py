"""Generate publication-quality architecture and evaluation workflow figure for the journal paper."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "STIXGeneral", "serif"],
    "mathtext.fontset": "stix",
})

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

# ----------------- SECTION A: conventional benchmark evaluation -----------------
def T(x, y, s, size, **kw):
    """top-anchored text so that blocks grow downwards and never collide with the heading above"""
    kw.setdefault("ha", "center")
    ax.text(x, y, s, fontsize=size, va="top", **kw)

rounded_box(1, 28, 98, 22.5, "#fafafa", "#cccccc", lw=1.0)
T(3, 50.0, "(a) Conventional benchmark evaluation (offline, end-host capture)", 8.5, ha="left", fontweight="bold", color="#8b0000")

# end-host capture
rounded_box(3, 29.5, 20, 15.5, C_BG_ERR, C_BORDER_ERR)
T(13, 44.4, "End-Host Capture", 7.5, fontweight="bold", color=C_TEXT)
T(13, 41.4, "Packets at the target\nhost interface", 6.2, color=C_MUTED)
T(13, 31.8, "InSDN CSV: 343,889 flows", 6, style="italic", color="#777777")
arrow(23.5, 37.5, 27.5, 37.5, color=C_BORDER_ERR)

# offline feature extraction
rounded_box(28, 29.5, 22, 15.5, "#fff8e7", "#e69f00")
T(39, 44.4, "Offline Feature Extractor", 7.5, fontweight="bold", color=C_TEXT)
T(39, 41.4, "(e.g., CICFlowMeter), 78 numeric\nfeatures: inter-arrival times,\nlength moments, TCP flags", 6.2, color=C_MUTED)
T(39, 33.4, "No per-flow counters\nat the controller (ONOS)", 6, fontweight="bold", color="#c0392b")
arrow(50.5, 37.5, 54.5, 37.5, color="#e69f00")

# random split
rounded_box(55, 29.5, 20, 15.5, C_BG_ERR, C_BORDER_ERR)
T(65, 44.4, "Evaluation Protocol", 7.5, fontweight="bold", color=C_TEXT)
T(65, 41.4, "Random 70:30 flow split\n48.7% of test rows duplicate\ntraining rows; same hosts\nin training and test", 6.2, color=C_MUTED)
T(65, 32.6, "Host and duplicate overlap", 6, fontweight="bold", color="#c0392b")
arrow(75.5, 37.5, 79.5, 37.5, color=C_BORDER_ERR)

# reported metric
rounded_box(80, 29.5, 17, 15.5, "#fbeeed", C_BORDER_ERR, lw=1.5)
T(88.5, 44.4, "Reported Metric", 7.5, fontweight="bold", color="#900")
T(88.5, 41.4, "Balanced accuracy\n0.9998 (InSDN,\nrandom split)", 6.8, fontweight="bold", color="#900")
T(88.5, 33.4, "Does not survive\nsource-IP-disjoint split", 6, style="italic", color="#777777")

# ----------------- SECTION B: this study -----------------
rounded_box(1, 1, 98, 25, "#fafafa", "#cccccc", lw=1.0)
T(3, 25.4, "(b) Controller observability and source-IP-disjoint evaluation (this study)", 8.5, ha="left", fontweight="bold", color="#005544")

rounded_box(3, 2.5, 23, 19.5, C_BG_REAL, C_BORDER_REAL)
T(14.5, 21.4, "SDN Control Channel", 7.5, fontweight="bold", color=C_TEXT)
T(14.5, 19.2, "OpenFlow 1.3 telemetry", 6.5, fontweight="bold", color="#006655")
T(14.5, 17.2, "- PacketIn: 0.68-1.29 per target\n  packet in 9 of 12 scenarios\n- FlowStats: MAC-pair counters\n- 0 FlowMods match a 5-tuple", 6.2, color=C_MUTED)
T(14.5, 5.6, "44 ONOS captures decoded", 6, style="italic", color="#006655")
arrow(26.5, 12.5, 30.5, 12.5, color=C_BORDER_REAL)

rounded_box(31, 2.5, 20, 19.5, C_BG_REAL, C_BORDER_REAL)
T(41, 21.4, "Window Featurizer", 7.5, fontweight="bold", color=C_TEXT)
T(41, 19.2, "22 features, W = 1 s, 5 s", 6.5, fontweight="bold", color=C_TEXT)
T(41, 17.2, "- Message counts\n- Header fractions, entropies\n- Flow-stats deltas\n- 4-window history", 6.2, color=C_MUTED)
T(41, 5.6, "Strict CSV-matched labels", 6, style="italic", color="#006655")
arrow(51.5, 12.5, 55.5, 12.5, color=C_BORDER_REAL)

rounded_box(56, 2.5, 22, 19.5, "#eef5fc", "#2a6f97")
T(67, 21.4, "Validity Checks", 7.5, fontweight="bold", color=C_TEXT)
T(67, 19.2, "Controller-side and flow-side", 6.5, fontweight="bold", color="#1a4f77")
T(67, 17.2, "- Any-IP and host-identity rules\n- Source-IP-disjoint, LOSGO\n- Deduplication\n- Forwarding-mode sensitivity", 6.2, color=C_MUTED)
T(67, 5.6, "Session and host confounds", 6, style="italic", color="#1a4f77")
arrow(78.5, 12.5, 82.5, 12.5, color="#2a6f97")

rounded_box(83, 2.5, 15, 19.5, "#e8f5e9", "#2e7d32", lw=1.5)
T(90.5, 21.4, "Source-IP groups", 7, fontweight="bold", color="#1b5e20")
T(90.5, 19.0, "BAcc 0.907 ± 0.085\n(worst 0.66)", 6.2, fontweight="bold", color="#1b5e20")
T(90.5, 13.6, "LOSGO alone:\nattacker recall 51.6%\nbenign host FPR 37.9%", 5.6, fontweight="bold", color="#c0392b")
T(90.5, 5.6, "InSDN, XGBoost", 5.8, style="italic", color="#555555")

plt.tight_layout()
fig.savefig(OUT_DIR / "fig_architecture.pdf", bbox_inches="tight")
print("fig_architecture.pdf successfully generated at", OUT_DIR / "fig_architecture.pdf")
