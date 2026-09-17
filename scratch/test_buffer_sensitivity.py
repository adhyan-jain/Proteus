"""Buffer capacity sensitivity experiment for Proteus closed-loop adaptation.

Evaluates three buffer capacity configurations:
1. Small:   N_ref = 10,000, N_recent = 2,500
2. Default: N_ref = 20,000, N_recent = 5,000
3. Large:   N_ref = 40,000, N_recent = 10,000

Measures Macro-F1, per-timestep latency, total runtime, and RSS memory for each configuration.
Saves results to results/buffer_sensitivity.json.
"""
import json
import logging
import resource
import time
from pathlib import Path

import numpy as np

from proteus.closed_loop_full import ClosedLoopOrchestrator, RealDataReplaySource
from proteus.evaluate_full import _load_day_split_data

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.buffer_sensitivity")

RESULTS_DIR = Path(__file__).parent.parent / "results"
CONFIGS = [
    {"name": "Small", "max_ref": 10000, "max_recent": 2500},
    {"name": "Default", "max_ref": 20000, "max_recent": 5000},
    {"name": "Large", "max_ref": 40000, "max_recent": 10000},
]


def run_buffer_sensitivity(seed=0):
    log.info("Loading CICIDS2017 temporal split dataset...")
    X_stable, y_stable, X_drifted, y_drifted, class_names = _load_day_split_data()

    rng = np.random.default_rng(seed)
    train_idx = rng.choice(len(X_stable), size=min(len(X_stable), 1_200_000), replace=False)
    X_train_full = X_stable[train_idx]
    y_train_full = y_stable[train_idx]

    source = RealDataReplaySource(
        X_stable, y_stable, X_drifted, y_drifted,
        n_windows=16, window_size=3000, drift_at_window=6, seed=seed
    )
    windows = [(t, X, y) for t, X, y, _ in source]

    results = []

    for cfg in CONFIGS:
        log.info(f"--- Running Configuration: {cfg['name']} (ref={cfg['max_ref']:,}, recent={cfg['max_recent']:,}) ---")
        t0 = time.time()
        orch = ClosedLoopOrchestrator(
            X_train_full, y_train_full, class_names,
            max_ref_samples=cfg["max_ref"],
            max_recent_samples=cfg["max_recent"]
        )

        closed_series = []
        step_latencies = []
        eval_rng = np.random.default_rng(123)

        for t, X, y in windows:
            t_step_start = time.time()
            X_eval, y_eval, X_fit, y_fit = ClosedLoopOrchestrator.split_eval_fit(
                X, y, 0.3, eval_rng)
            mf1_before, mf1_after = orch.step(t, X_eval, y_eval, X_fit, y_fit)
            t_step_elapsed = time.time() - t_step_start
            closed_series.append({"timestep": t, "macro_f1": mf1_after})
            if t >= 6:
                step_latencies.append(t_step_elapsed)

        wall_clock = time.time() - t0
        peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

        post_drift_f1s = [p["macro_f1"] for p in closed_series[6:]]
        final_f1 = closed_series[-1]["macro_f1"]
        mean_post_drift_f1 = float(np.mean(post_drift_f1s))

        log.info(f"[{cfg['name']}] Wall-clock: {wall_clock:.1f}s | Mean Drift Step Latency: {np.mean(step_latencies):.2f}s | Final F1: {final_f1:.4f} | Post-Drift Mean F1: {mean_post_drift_f1:.4f}")

        results.append({
            "config_name": cfg["name"],
            "max_ref_samples": cfg["max_ref"],
            "max_recent_samples": cfg["max_recent"],
            "wall_clock_seconds": wall_clock,
            "mean_adaptation_latency_seconds": float(np.mean(step_latencies)),
            "peak_rss_mb": peak_rss_mb,
            "final_macro_f1": final_f1,
            "post_drift_mean_macro_f1": mean_post_drift_f1,
            "series": closed_series
        })

    summary = {
        "seed": seed,
        "configurations": results
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "buffer_sensitivity.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Wrote buffer sensitivity results to {out_path}")
    return summary


if __name__ == "__main__":
    run_buffer_sensitivity(seed=0)
