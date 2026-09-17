"""Stage 7: full three-condition evaluation (baseline / static-augmentation / closed-loop)
against an identical real drift schedule, at full scale.

**Scope honesty, read before trusting a number from this module**: the ground rules for this
project call for a minimum of 5 random seeds with confidence intervals, evaluated against live
Mininet/Ryu traffic. Neither is what a single call to `run_stage7(n_seeds=1)` gives you --
- Traffic source is `proteus.closed_loop_full.RealDataReplaySource` (real CICIDS2017 data, real
  Mon-Thu vs. Friday temporal drift), not live Mininet traffic -- see that module's own
  docstring for why (Mininet needs root, not available in this environment).
- A full-scale closed-loop run retrains a 100-tree Random Forest on up to ~1.5M+ rows at every
  drift-fired timestep -- each retrain alone takes several minutes. `n_seeds=5` is a genuinely
  multi-hour job at this scale, not something to run casually. `run_stage7()` supports
  `n_seeds` as a parameter specifically so a single real seed can be run and reported honestly
  as n=1 (no confidence interval claimed) while a full 5-seed sweep is queued separately with
  its own wall-clock budget -- never report a single run's number as if it had a confidence
  interval behind it.
"""
import json
import logging
import time
from pathlib import Path

import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

import numpy as np

from proteus.baseline_full import train_and_evaluate, build_static_augmented_set
from proteus.closed_loop_full import ClosedLoopOrchestrator, RealDataReplaySource
from sklearn.metrics import f1_score, classification_report

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.evaluate_full")

RESULTS_DIR = Path(__file__).parent.parent / "results"

N_WINDOWS = 16
WINDOW_SIZE = 3000
DRIFT_AT_WINDOW = 6


def _load_day_split_data():
    """Real Mon-Thu (stable) vs. Friday (drifted) pools, loaded once, matching Stage 4's
    validated temporal-drift approach -- reused here rather than re-derived differently."""
    import gc
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder
    from proteus.data_full import load_cicids2017_raw, clean_and_unify_cicids2017, \
        get_feature_schema

    raw = load_cicids2017_raw()
    df = clean_and_unify_cicids2017(raw)
    del raw
    gc.collect()
    schema = get_feature_schema(df)
    df = pd.get_dummies(df, columns=["protocol"])
    feature_cols = [c for c in df.columns if c not in ("label", "__source_day") and
                     not any(c == ic for ic in schema["identifier_columns"])]
    le = LabelEncoder()
    df["_y"] = le.fit_transform(df["label"])
    class_names = list(le.classes_)

    stable_mask = df["__source_day"].isin(["Monday", "Tuesday", "Wednesday", "Thursday"])
    drifted_mask = df["__source_day"] == "Friday"
    X_stable = df[stable_mask][feature_cols].astype(np.float32).values
    y_stable = df[stable_mask]["_y"].values
    X_drifted = df[drifted_mask][feature_cols].astype(np.float32).values
    y_drifted = df[drifted_mask]["_y"].values
    del df
    gc.collect()
    return X_stable, y_stable, X_drifted, y_drifted, class_names


def _eval_frozen(clf, class_names, eval_windows):
    """Score a frozen classifier on the shared held-out eval partition of each window (NOT the
    full window) -- same rows the closed-loop condition is scored on, for a fair comparison."""
    series = []
    for t, X_eval, y_eval in eval_windows:
        y_pred = clf.predict(X_eval)
        mf1 = float(f1_score(y_eval, y_pred, labels=list(range(len(class_names))),
                              average="macro", zero_division=0))
        series.append({"timestep": t, "macro_f1": mf1})
    return series


def _per_class_breakdown(y_true, y_pred, class_names):
    """Real per-class F1 + active-class count for one window, used to honestly reconcile the
    25-class Macro-F1 against an active-class Macro-F1 (no hardcoded active-class count)."""
    report = classification_report(y_true, y_pred, labels=list(range(len(class_names))),
                                    target_names=class_names, output_dict=True, zero_division=0)
    per_class_f1 = {c: float(report[c]["f1-score"]) for c in class_names}
    support = {c: int(report[c]["support"]) for c in class_names}
    active_classes = [c for c in class_names if support[c] > 0]
    active_f1s = [per_class_f1[c] for c in active_classes]
    active_class_macro_f1 = float(np.mean(active_f1s)) if active_f1s else 0.0
    macro_f1_25class = float(report["macro avg"]["f1-score"])
    return {
        "n_active_classes": len(active_classes),
        "active_classes": active_classes,
        "per_class_f1": per_class_f1,
        "support": support,
        "active_class_macro_f1": active_class_macro_f1,
        "macro_f1_25class": macro_f1_25class,
        "theoretical_ceiling": len(active_classes) / len(class_names),
    }


def run_one_seed(seed, X_stable, y_stable, X_drifted, y_drifted, class_names):
    t0 = time.time()
    rng = np.random.default_rng(seed)
    train_idx = rng.choice(len(X_stable), size=min(len(X_stable), 1_200_000), replace=False)
    X_train_full = X_stable[train_idx]
    y_train_full = y_stable[train_idx]

    # Fixed window schedule (same real windows for all 3 conditions, this seed) --
    # pre-materialize from a RealDataReplaySource so baseline/static-aug (frozen, no retraining
    # side effects) and closed-loop (stateful, retrains) all see identical data.
    source = RealDataReplaySource(X_stable, y_stable, X_drifted, y_drifted,
                                   n_windows=N_WINDOWS, window_size=WINDOW_SIZE,
                                   drift_at_window=DRIFT_AT_WINDOW, seed=seed)
    windows = [(t, X, y) for t, X, y, _ in source]
    drift_schedule_timesteps = list(range(DRIFT_AT_WINDOW, N_WINDOWS))

    # Shared eval/fit split, computed ONCE per window and reused identically across all 3
    # conditions -- fixes the prior asymmetry where baseline/static were scored on the full
    # window while closed-loop was scored only on its internal 30% held-out partition. All three
    # conditions now score on the exact same rows.
    split_rng = np.random.default_rng(123)
    split_windows = [
        (t,) + ClosedLoopOrchestrator.split_eval_fit(X, y, 0.3, split_rng)
        for t, X, y in windows
    ]  # (t, X_eval, y_eval, X_fit, y_fit)
    eval_windows = [(t, X_eval, y_eval) for t, X_eval, y_eval, _, _ in split_windows]

    log.info(f"[seed={seed}] Training baseline classifier ({len(X_train_full):,} rows)...")
    clf_baseline, _ = train_and_evaluate(None, X_train_full, y_train_full,
                                          X_train_full[:1000], y_train_full[:1000], class_names)
    baseline_series = _eval_frozen(clf_baseline, class_names, eval_windows)

    log.info(f"[seed={seed}] Building + training static-augmentation classifier...")
    X_aug, y_aug, _ = build_static_augmented_set(X_train_full, y_train_full, class_names)
    clf_static, _ = train_and_evaluate(None, X_aug, y_aug, X_aug[:1000], y_aug[:1000],
                                        class_names)
    static_series = _eval_frozen(clf_static, class_names, eval_windows)

    log.info(f"[seed={seed}] Running closed-loop orchestrator...")
    orch = ClosedLoopOrchestrator(X_train_full, y_train_full, class_names)
    closed_series = []
    for t, X_eval, y_eval, X_fit, y_fit in split_windows:
        mf1_before, mf1_after = orch.step(t, X_eval, y_eval, X_fit, y_fit)
        closed_series.append({"timestep": t, "macro_f1": mf1_after})
    drift_events = orch.drift_events
    retrain_events = orch.retrain_events
    gate_log = orch.gate.entries

    # Real per-class F1 breakdown on the FINAL window's eval partition, for all 3 conditions,
    # reconciling the 25-class Macro-F1 against an honestly-computed active-class Macro-F1
    # (no hardcoded active-class count -- see results/stage7_per_class_f1.json).
    t_final, X_eval_final, y_eval_final = eval_windows[-1]
    per_class = {
        "baseline": _per_class_breakdown(y_eval_final, clf_baseline.predict(X_eval_final),
                                          class_names),
        "static_augmentation": _per_class_breakdown(y_eval_final, clf_static.predict(X_eval_final),
                                                      class_names),
        "closed_loop": _per_class_breakdown(y_eval_final, orch.clf.predict(X_eval_final),
                                             class_names),
    }
    for cond in per_class:
        per_class[cond]["timestep"] = t_final

    del orch
    import torch
    torch.cuda.empty_cache()  # free this seed's GPU-resident GAN before the next seed starts
    # a fresh one -- this machine's 8GB GPU is sometimes shared with other real GPU workloads.

    return {
        "seed": seed,
        "wall_clock_seconds": time.time() - t0,
        "n_train_rows": int(len(X_train_full)),
        "drift_schedule_timesteps": drift_schedule_timesteps,
        "baseline_macro_f1_series": baseline_series,
        "static_augmentation_macro_f1_series": static_series,
        "closed_loop_macro_f1_series": closed_series,
        "drift_events": drift_events,
        "retrain_events": retrain_events,
        "gate_log": gate_log,
        "per_class_breakdown": per_class,
    }


def run_stage7(n_seeds=1, seeds=None):
    if seeds is None:
        seeds = list(range(n_seeds))
    log.info(f"Stage 7 evaluation: {len(seeds)} seed(s) -- {seeds}. NOTE: traffic source is "
             f"RealDataReplaySource (real data, real temporal drift), NOT live Mininet traffic "
             f"-- see this module's docstring.")

    X_stable, y_stable, X_drifted, y_drifted, class_names = _load_day_split_data()

    results = []
    for seed in seeds:
        r = run_one_seed(seed, X_stable, y_stable, X_drifted, y_drifted, class_names)
        log.info(f"[seed={seed}] done in {r['wall_clock_seconds']:.1f}s")
        results.append(r)

    def final_f1(series):
        return series[-1]["macro_f1"]

    summary = {
        "n_seeds": len(seeds), "seeds": seeds,
        "traffic_source": "RealDataReplaySource",
        "is_live_mininet_traffic": False,
        "confidence_interval_valid": len(seeds) >= 5,
        "leakage_fix_applied": True,
        "per_seed_results": results,
        "final_macro_f1_baseline": [final_f1(r["baseline_macro_f1_series"]) for r in results],
        "final_macro_f1_static_augmentation":
            [final_f1(r["static_augmentation_macro_f1_series"]) for r in results],
        "final_macro_f1_closed_loop": [final_f1(r["closed_loop_macro_f1_series"]) for r in
                                        results],
    }
    if len(seeds) >= 5:
        for key in ("final_macro_f1_baseline", "final_macro_f1_static_augmentation",
                    "final_macro_f1_closed_loop"):
            vals = np.array(summary[key])
            mean, std = float(vals.mean()), float(vals.std(ddof=1))
            ci95 = 1.96 * std / np.sqrt(len(vals))
            summary[key + "_mean"] = mean
            summary[key + "_ci95"] = ci95
    else:
        log.warning(f"Only {len(seeds)} seed(s) run -- NOT reporting a confidence interval "
                    f"(this project's rule requires >=5 seeds for that). Report per-seed "
                    f"numbers as single-run results, not as a statistically validated mean.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "stage7_evaluation.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Wrote {RESULTS_DIR / 'stage7_evaluation.json'}")

    per_class_out = {
        "n_seeds": len(seeds), "seeds": seeds,
        "note": "Per-class F1 breakdown on the final window's held-out eval partition, per seed "
                "and condition. n_active_classes/active_class_macro_f1 are computed directly "
                "from sklearn's classification_report support counts, not hardcoded.",
        "per_seed_per_class": [
            {"seed": r["seed"], **r["per_class_breakdown"]} for r in results
        ],
    }
    with open(RESULTS_DIR / "stage7_per_class_f1.json", "w") as f:
        json.dump(per_class_out, f, indent=2)
    log.info(f"Wrote {RESULTS_DIR / 'stage7_per_class_f1.json'}")

    return summary


if __name__ == "__main__":
    run_stage7(n_seeds=1)
