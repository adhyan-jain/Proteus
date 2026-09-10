"""Proteus read-only local JSON API.

Serves results/results.pkl (the demo-scale closed-loop experiment run) and a precomputed
summary of the full-scale datasets (proteus/data_full.py) as small, screen-shaped JSON
endpoints. No auth, no writes, local-only — this sits next to the Next.js dev/prod server
purely so the new frontend has something real to read from instead of the Streamlit app's
in-process pickle access.

Run: .venv/bin/uvicorn api.server:app --reload --port 8000   (from repo root)
"""
import json
import pickle
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PKL = ROOT / "results" / "results.pkl"
DATASETS_CACHE = Path(__file__).resolve().parent / "cache" / "datasets_summary.json"

app = FastAPI(title="Proteus API", description="Read-only local API over Proteus research results.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache = {"mtime": None, "data": None}


def _load_results() -> Optional[dict]:
    if not RESULTS_PKL.exists():
        return None
    mtime = RESULTS_PKL.stat().st_mtime
    if _cache["mtime"] != mtime:
        with open(RESULTS_PKL, "rb") as f:
            _cache["data"] = pickle.load(f)
        _cache["mtime"] = mtime
    return _cache["data"]


def _not_available(reason: str):
    return {"available": False, "reason": reason}


@app.get("/api/health")
def health():
    d = _load_results()
    return {
        "status": "ok",
        "results_available": d is not None,
        "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/api/experiments/latest")
def experiments_latest():
    """Top-level summary of the most recent (only) experiment run: data source, class
    schema, rare classes, timestep count, drift schedule, runtime."""
    d = _load_results()
    if d is None:
        return _not_available("No results/results.pkl found. Run `.venv/bin/python run_pipeline.py`.")
    return {
        "available": True,
        "data_source": d["data_source"],
        "class_names": d["class_names"],
        "class_distribution": d["class_distribution"],
        "n_features": d["n_features"],
        "rare_classes": d["rare_classes"],
        "n_timesteps": d["n_timesteps"],
        "drift_schedule": d["drift_schedule"],
        "gan_degraded": d["gan_degraded"],
        "gan_error": d.get("gan_error"),
        "runtime_seconds": d["runtime_seconds"],
        "single_seed": True,
        "conditions": list(d["conditions"].keys()),
    }


@app.get("/api/experiments/conditions")
def experiments_conditions():
    """Per-timestep macro-F1 and per-class F1 for baseline / static_augmentation /
    closed_loop, aligned by timestep index, for the Experiments comparison screen."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    out = {}
    for name, cond in d["conditions"].items():
        out[name] = {
            "macro_f1": cond["macro_f1"],
            "per_class_f1": cond["per_class_f1"],
        }
    return {
        "available": True,
        "class_names": d["class_names"],
        "drift_schedule": d["drift_schedule"],
        "retrain_timesteps": [e["timestep"] for e in d["retrain_events"] if "error" not in e],
        "conditions": out,
    }


@app.get("/api/experiments/final-reports")
def experiments_final_reports():
    """Final held-out classification_report per condition (precision/recall/f1/support
    per class), for the class-performance matrix on Experiments / Overview."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {"available": True, "class_names": d["class_names"], "final_reports": d["final_reports"]}


@app.get("/api/drift/events")
def drift_events():
    """KS-test drift detector firing log: statistic, p-value, alpha, fired, per timestep."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {
        "available": True,
        "method": "Kolmogorov-Smirnov test on classifier confidence distribution",
        "events": d["drift_events"],
        "drift_schedule": d["drift_schedule"],
        "retrain_events": d["retrain_events"],
    }


@app.get("/api/gan/loss")
def gan_loss():
    """WGAN-GP generator/critic loss log across training steps, for the Synthetic Lab."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {
        "available": True,
        "degraded": d["gan_degraded"],
        "error": d.get("gan_error"),
        "rare_classes": d["rare_classes"],
        "loss_log": d["gan_loss_log"],
    }


@app.get("/api/gate/log")
def gate_log():
    """Fidelity-gate (MMD) admission log: static-augmentation gate (pre-stream, one-shot)
    plus closed-loop gate (during the simulated stream)."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {
        "available": True,
        "method": "Maximum Mean Discrepancy (MMD) vs threshold",
        "threshold": 0.25,
        "static_gate_log": d["static_gate_log"],
        "closed_loop_gate_log": d["closed_loop_gate_log"],
    }


@app.get("/api/adaptation/events")
def adaptation_events():
    """Closed-loop retrain events (drift -> retrain), each with before/after macro-F1 at
    that timestep and count of synthetic samples admitted into the retrain set."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {"available": True, "retrain_events": d["retrain_events"]}


@app.get("/api/metrics/final")
def metrics_final():
    """Baseline classifier's final held-out eval (confusion matrix + report), the
    pre-stream reference point."""
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    be = d["baseline_eval"]
    return {
        "available": True,
        "class_names": d["class_names"],
        "report": be["report"],
        "confusion_matrix": be["confusion_matrix"],
        "macro_f1": be["macro_f1"],
    }


@app.get("/api/topology")
def topology():
    """No live Mininet/Ryu controller is deployed yet (separate in-progress workstream).
    Explicit not-available response rather than fabricated topology."""
    return _not_available(
        "No live SDN controller connected. The Mininet/Ryu deployment is a separate, "
        "in-progress workstream and is not wired up in this build."
    )


@app.get("/api/datasets/summary")
def datasets_summary():
    """Precomputed class distributions / row counts / schema for the full-scale
    CICIDS2017 and InSDN datasets (proteus/data_full.py), for the Datasets/Models screen."""
    if not DATASETS_CACHE.exists():
        return _not_available(
            "Dataset summary not precomputed yet. Run "
            "`.venv/bin/python api/precompute_datasets.py` (takes several minutes)."
        )
    return {"available": True, **json.loads(DATASETS_CACHE.read_text())}


@app.get("/api/models")
def models():
    """Model/version context. Only the demo-scale model (trained inside the single
    results.pkl run) currently exists; no full-scale or InSDN-trained model exists yet."""
    d = _load_results()
    demo_model = None
    if d is not None:
        demo_model = {
            "name": "proteus-demo-classifier",
            "trained_on": d["data_source"],
            "n_features": d["n_features"],
            "class_names": d["class_names"],
            "conditions_trained": list(d["conditions"].keys()),
        }
    return {
        "demo_model": demo_model,
        "full_scale_model": _not_available(
            "No classifier has been trained on the full-scale CICIDS2017/InSDN pipeline "
            "yet -- proteus/data_full.py is a data-stage-only workstream so far."
        ),
        "insdn_model": _not_available("No InSDN-trained model exists yet."),
    }
