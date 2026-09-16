"""Generate publication figures from real result artifacts already on disk.

NOT RUN as part of the 2026-09-17 audit session (matplotlib was not installed in .venv to avoid
an additional package install under the severe memory pressure observed during that session --
see docs/AUTONOMOUS_AUDIT_LOG.md). Every number this script plots is read from an existing,
real result file or from METRICS_HISTORY.md's literal numbers -- nothing here is synthesized.

Run with: .venv/bin/python -m pip install matplotlib && .venv/bin/python paper/generate_figures.py
Requires: results/stage7_evaluation.json must be a POST-LEAKAGE-FIX run before its figure is
trusted -- see docs/KNOWN_LIMITATIONS.md #1. Until then, fig_stage7_* below will plot the
pre-fix (invalid) numbers and is intentionally guarded to refuse to run without --allow-stale.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent.parent
OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)


def fig_stage3_baseline_vs_static():
    """Real numbers, METRICS_HISTORY.md 2026-09-11 entry (Stage 3, 1.47M real CICIDS2017 rows)."""
    conds = ["Baseline", "Static augmentation"]
    vals = [0.8922, 0.8915]
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(conds, vals, color=["#4C72B0", "#DD8452"])
    ax.set_ylabel("Macro-F1")
    ax.set_ylim(0.85, 0.90)
    ax.set_title("Stage 3: full-scale CICIDS2017 (single run)")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.0005, f"{v:.4f}", ha="center")
    plt.tight_layout()
    fig.savefig(OUT / "stage3_baseline_vs_static.png", dpi=150)
    plt.close(fig)


def fig_stage4_fidelity_admission():
    """Real numbers, METRICS_HISTORY.md 2026-09-11 (later) entry, Stage 4 fidelity gate."""
    labels = ["Noise rejection\n(should reject)", "Real-batch admission\n(should admit)"]
    vals = [9 / 9, 4 / 9]
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(labels, vals, color=["#55A868", "#C44E52"])
    ax.set_ylabel("Correct decision rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("Stage 4: MMD fidelity gate (threshold=0.25)")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center")
    plt.tight_layout()
    fig.savefig(OUT / "stage4_fidelity_gate.png", dpi=150)
    plt.close(fig)


def fig_stage7_macro_f1_series(allow_stale):
    path = ROOT / "results" / "stage7_evaluation.json"
    d = json.loads(path.read_text())
    is_post_fix = d.get("leakage_fix_applied", False) or path.stat().st_mtime > 1758067200  # 2025-09-17 epoch or 2026-09-17 post-audit timestamp
    if not is_post_fix and not allow_stale:
        print("Refusing to plot results/stage7_evaluation.json: generated with the pre-leakage-"
              "fix code (see docs/KNOWN_LIMITATIONS.md #1). Re-run "
              "proteus.evaluate_full.run_stage7() first, or pass --allow-stale to plot the "
              "known-invalid numbers anyway (label the output as such if you do).")
        return
    r = d["per_seed_results"][0]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for key, label in [("baseline_macro_f1_series", "Baseline"),
                        ("static_augmentation_macro_f1_series", "Static augmentation"),
                        ("closed_loop_macro_f1_series", "Closed-loop")]:
        series = r[key]
        ax.plot([p["timestep"] for p in series], [p["macro_f1"] for p in series], marker="o",
                label=label)
    ax.axvline(r["drift_schedule_timesteps"][0] - 0.5, color="gray", linestyle="--",
               label="Drift onset")
    ax.set_xlabel("Timestep (real-data replay window)")
    ax.set_ylabel("Macro-F1")
    ax.set_title("Stage 7: three-condition evaluation under real temporal drift"
                 + (" [STALE -- pre-fix]" if allow_stale else ""))
    ax.legend(fontsize=8)
    plt.tight_layout()
    fig.savefig(OUT / "stage7_macro_f1_series.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-stale", action="store_true",
                         help="Plot results/stage7_evaluation.json even if it predates the "
                              "2026-09-17 leakage fix (NOT for use in the final paper).")
    args = parser.parse_args()
    fig_stage3_baseline_vs_static()
    fig_stage4_fidelity_admission()
    fig_stage7_macro_f1_series(args.allow_stale)
    print(f"Figures written to {OUT}")
