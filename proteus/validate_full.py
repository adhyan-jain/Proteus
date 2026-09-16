"""Stage 4: drift detector + fidelity gate, validated at real scale against CICIDS2017's actual
temporal and class structure -- not synthetic sanity-check batches.

Reuses `proteus.drift.detect_drift` and `proteus.fidelity.compute_mmd`/`admit` as-is (both are
already dataset-agnostic pure functions -- no need to fork or rewrite them for full scale).

## Drift detector validation: a real temporal split, not injected drift

CICIDS2017 has a well-known real temporal structure: Monday's capture is pure BENIGN traffic;
Tuesday-Thursday introduce brute-force/DoS/web-attack/infiltration patterns; Friday introduces
PortScan, DDoS, and Botnet -- attack families that are *absent* from Monday-Thursday entirely.
This gives a genuine, real known-drifted holdout (Friday) versus a genuine known-stable holdout
(a fresh random sample from Monday-Thursday, the same days the classifier trained on) --
real data, real temporal structure, not a synthetic distribution shift.

## Fidelity gate validation: real synthetic batches vs. real noise

Same test as the demo, at full scale: a real WGAN-GP-generated batch (admitted classes only,
see `gan_full.GAN_ADMIT_CLASSES`) against real recent held-out data should be admitted; a batch
of injected Gaussian noise at the same shape should be rejected.
"""
import json
import logging
import time
from pathlib import Path

from proteus.config import DEFAULT_N_JOBS  # noqa: F401 -- must import before numpy/torch/sklearn to cap BLAS/OMP threads

import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier

from proteus import drift as drift_mod, fidelity as fidelity_mod

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.validate_full")

RESULTS_DIR = Path(__file__).parent.parent / "results"
CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints" / "gan_full"

MONDAY_THROUGH_THURSDAY = ["Monday", "Tuesday", "Wednesday", "Thursday"]
FRIDAY = "Friday"


def _confidence(clf, X):
    return clf.predict_proba(X).max(axis=1)


def validate_drift_detector():
    from proteus.data_full import (
        load_cicids2017_raw, clean_and_unify_cicids2017, get_feature_schema)
    from sklearn.preprocessing import LabelEncoder
    import pandas as pd

    log.info("Loading + cleaning CICIDS2017 for a real temporal (day-based) split...")
    raw = load_cicids2017_raw()
    df = clean_and_unify_cicids2017(raw)
    schema = get_feature_schema(df)

    df = pd.get_dummies(df, columns=["protocol"])
    feature_cols = [c for c in df.columns
                     if c not in ("label", "__source_day") and
                     not any(c == ic for ic in schema["identifier_columns"])]

    le = LabelEncoder()
    df["_y"] = le.fit_transform(df["label"])

    train_mask = df["__source_day"].isin(MONDAY_THROUGH_THURSDAY)
    friday_mask = df["__source_day"] == FRIDAY
    log.info(f"Mon-Thu rows: {int(train_mask.sum()):,}  Friday rows: {int(friday_mask.sum()):,}")

    df_train = df[train_mask]
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(df_train))
    split = int(len(df_train) * 0.8)
    fit_idx, stable_holdout_idx = idx[:split], idx[split:]

    X_fit = df_train.iloc[fit_idx][feature_cols].astype(np.float32).values
    y_fit = df_train.iloc[fit_idx]["_y"].values
    X_stable = df_train.iloc[stable_holdout_idx][feature_cols].astype(np.float32).values

    X_friday = df[friday_mask][feature_cols].astype(np.float32).values

    friday_labels = sorted(df[friday_mask]["label"].unique())
    monthu_labels = set(df[train_mask]["label"].unique())
    friday_only = [c for c in friday_labels if c not in monthu_labels]
    log.info(f"Attack classes present Friday but absent Monday-Thursday (genuine unseen "
             f"patterns): {friday_only}")

    log.info(f"Training reference classifier on Mon-Thu ({len(X_fit):,} rows)...")
    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=DEFAULT_N_JOBS)
    clf.fit(X_fit, y_fit)

    ref_conf = _confidence(clf, X_fit[:min(50000, len(X_fit))])
    stable_conf = _confidence(clf, X_stable)
    friday_conf = _confidence(clf, X_friday)

    stable_result = drift_mod.detect_drift(stable_conf, ref_conf)
    friday_result = drift_mod.detect_drift(friday_conf, ref_conf)

    correctly_separated = (not stable_result["fired"]) and friday_result["fired"]
    log.info(f"Known-stable (Mon-Thu holdout) drift result: fired={stable_result['fired']} "
             f"statistic={stable_result['statistic']:.4f} p={stable_result['p_value']:.6g}")
    log.info(f"Known-drifted (Friday, real unseen attack families) drift result: "
             f"fired={friday_result['fired']} statistic={friday_result['statistic']:.4f} "
             f"p={friday_result['p_value']:.6g}")
    log.info(f"Correctly separated known-good vs. known-bad: {correctly_separated}")

    return {
        "train_days": MONDAY_THROUGH_THURSDAY, "holdout_day": FRIDAY,
        "n_train_rows": int(len(X_fit)), "n_stable_holdout_rows": int(len(X_stable)),
        "n_friday_rows": int(len(X_friday)),
        "friday_only_attack_classes": friday_only,
        "known_stable_result": stable_result, "known_drifted_result": friday_result,
        "correctly_separated": bool(correctly_separated),
    }


def validate_fidelity_gate():
    from proteus.data_full import load_data_full
    from proteus.gan_full import WGANGPFull, GAN_ADMIT_CLASSES

    log.info("Loading full CICIDS2017 data for fidelity gate validation...")
    d = load_data_full()
    X_train, y_train = d["X_train"], d["y_train"]
    class_names = d["class_names"]
    name_to_idx = {c: i for i, c in enumerate(class_names)}

    ckpt_files = sorted(CHECKPOINT_DIR.glob("epoch_*.pt"),
                         key=lambda p: int(p.stem.split("_")[1]))
    ckpt = torch.load(ckpt_files[-1], map_location="cuda", weights_only=False)
    gan = WGANGPFull(X_train.shape[1], ckpt["class_labels"], ckpt["feature_mean"],
                      ckpt["feature_std"], device="cuda")
    gan.G.load_state_dict(ckpt["generator"])
    gan.D.load_state_dict(ckpt["critic"])

    threshold = 0.25  # same threshold used in the demo (proteus/pipeline.py), kept consistent
    entries = []
    for cname in GAN_ADMIT_CLASSES:
        c = name_to_idx[cname]
        real_recent = X_train[y_train == c].astype(np.float32)
        synth = gan.generate_synthetic_batch(c, n_samples=min(200, len(real_recent)))
        score = fidelity_mod.compute_mmd(synth, real_recent)
        admitted = fidelity_mod.admit(score, threshold)
        entries.append({"class": cname, "kind": "real_synthetic_batch", "mmd_score": score,
                         "admitted": admitted, "expected_admitted": True})
        log.info(f"[real synthetic] {cname}: mmd={score:.4f} admitted={admitted} "
                 f"(expected: admitted)")

        noise = np.random.default_rng(0).normal(
            loc=real_recent.mean(axis=0), scale=real_recent.std(axis=0) * 5,
            size=(min(200, len(real_recent)), real_recent.shape[1])).astype(np.float32)
        noise_score = fidelity_mod.compute_mmd(noise, real_recent)
        noise_admitted = fidelity_mod.admit(noise_score, threshold)
        entries.append({"class": cname, "kind": "injected_noise", "mmd_score": noise_score,
                         "admitted": noise_admitted, "expected_admitted": False})
        log.info(f"[injected noise]   {cname}: mmd={noise_score:.4f} admitted={noise_admitted} "
                 f"(expected: rejected)")

    n_correct = sum(1 for e in entries if e["admitted"] == e["expected_admitted"])
    log.info(f"\nGate correctly classified {n_correct}/{len(entries)} "
             f"(real-synthetic should admit, noise should reject)")

    return {"threshold": threshold, "entries": entries,
            "n_correct": n_correct, "n_total": len(entries)}


def run_stage4():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    drift_result = validate_drift_detector()
    gate_result = validate_fidelity_gate()

    summary = {"drift_detector_validation": drift_result,
               "fidelity_gate_validation": gate_result,
               "wall_clock_seconds": time.time() - t0}
    with open(RESULTS_DIR / "stage4_validation.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"\nWrote {RESULTS_DIR / 'stage4_validation.json'}")
    log.info(f"\nSANITY CHECK: drift detector correctly separated = "
             f"{drift_result['correctly_separated']}; "
             f"fidelity gate correct = {gate_result['n_correct']}/{gate_result['n_total']}")
    return summary


if __name__ == "__main__":
    run_stage4()
