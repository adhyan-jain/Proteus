"""Stage 7 GAN/fidelity-gate attribution ablation (Priority 4 of the 2026-09-17 audit
remediation).

Motivation: the paper credited "MMD fidelity gating" for post-drift recovery, but
results/stage7_evaluation.json's own retrain_events[0] shows the largest single recovery jump
(timestep 6) happened with n_synthetic_admitted=0 -- before the GAN pipeline contributed
anything. This script isolates the contribution of each mechanism directly, on the identical
window stream and eval/fit split used by the main Stage 7 run (same seed=0, same
RealDataReplaySource config, same split_eval_fit(seed=123)), so the three conditions below are
comparable to each other and to the closed-loop series in stage7_evaluation.json.

Conditions:
  1. incremental_only        -- ClosedLoopOrchestrator(use_gan=False)
  2. incremental_gan_no_gate -- ClosedLoopOrchestrator(use_gan=True, use_fidelity_gate=False)
  3. incremental_gan_gated   -- ClosedLoopOrchestrator(use_gan=True, use_fidelity_gate=True),
                                 the current default/full pipeline, rerun here for a clean
                                 side-by-side comparison under identical conditions.

Single seed, diagnostic ablation -- not a headline statistical result (no n=5 requirement here,
but label it as single-seed/diagnostic wherever it's cited in the paper).
"""
import json
import logging
from pathlib import Path

import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

import numpy as np
import torch

from proteus.evaluate_full import _load_day_split_data, N_WINDOWS, WINDOW_SIZE, DRIFT_AT_WINDOW
from proteus.closed_loop_full import ClosedLoopOrchestrator, RealDataReplaySource

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("scripts.run_gan_ablation")

RESULTS_DIR = Path(__file__).parent.parent / "results"
SEED = 0


def _run_condition(name, use_gan, use_fidelity_gate, X_train_full, y_train_full, class_names,
                    split_windows):
    log.info(f"--- Condition: {name} (use_gan={use_gan}, use_fidelity_gate={use_fidelity_gate}) ---")
    orch = ClosedLoopOrchestrator(X_train_full, y_train_full, class_names,
                                   use_gan=use_gan, use_fidelity_gate=use_fidelity_gate)
    series = []
    for t, X_eval, y_eval, X_fit, y_fit in split_windows:
        mf1_before, mf1_after = orch.step(t, X_eval, y_eval, X_fit, y_fit)
        series.append({"timestep": t, "macro_f1_before": mf1_before, "macro_f1_after": mf1_after})
    result = {
        "condition": name,
        "use_gan": use_gan,
        "use_fidelity_gate": use_fidelity_gate,
        "macro_f1_series": series,
        "final_macro_f1": series[-1]["macro_f1_after"],
        "post_drift_mean_macro_f1": float(np.mean(
            [s["macro_f1_after"] for s in series if s["timestep"] >= DRIFT_AT_WINDOW])),
        "retrain_events": orch.retrain_events,
    }
    del orch
    torch.cuda.empty_cache()
    return result


def main():
    X_stable, y_stable, X_drifted, y_drifted, class_names = _load_day_split_data()

    rng = np.random.default_rng(SEED)
    train_idx = rng.choice(len(X_stable), size=min(len(X_stable), 1_200_000), replace=False)
    X_train_full = X_stable[train_idx]
    y_train_full = y_stable[train_idx]

    source = RealDataReplaySource(X_stable, y_stable, X_drifted, y_drifted,
                                   n_windows=N_WINDOWS, window_size=WINDOW_SIZE,
                                   drift_at_window=DRIFT_AT_WINDOW, seed=SEED)
    windows = [(t, X, y) for t, X, y, _ in source]

    split_rng = np.random.default_rng(123)
    split_windows = [
        (t,) + ClosedLoopOrchestrator.split_eval_fit(X, y, 0.3, split_rng)
        for t, X, y in windows
    ]

    conditions = [
        ("incremental_only", False, False),
        ("incremental_gan_no_gate", True, False),
        ("incremental_gan_gated", True, True),
    ]
    results = {}
    for name, use_gan, use_fidelity_gate in conditions:
        results[name] = _run_condition(name, use_gan, use_fidelity_gate, X_train_full,
                                        y_train_full, class_names, split_windows)
        log.info(f"[{name}] final_macro_f1={results[name]['final_macro_f1']:.4f} "
                 f"post_drift_mean={results[name]['post_drift_mean_macro_f1']:.4f}")

    summary = {
        "seed": SEED,
        "note": "Single-seed diagnostic ablation isolating incremental-real-data adaptation "
                "from GAN synthetic admission and MMD fidelity gating. Not a headline "
                "statistical result.",
        "n_windows": N_WINDOWS, "window_size": WINDOW_SIZE, "drift_at_window": DRIFT_AT_WINDOW,
        "conditions": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "gan_ablation.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Wrote {RESULTS_DIR / 'gan_ablation.json'}")


if __name__ == "__main__":
    main()
