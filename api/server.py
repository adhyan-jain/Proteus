"""Proteus local JSON API & Online Inference Service.

Serves:
1. Production inference endpoints (/predict, /model, /health, /version, /metrics)
2. Research results endpoints (/api/experiments/..., /api/drift/..., /api/gate/...) for the Next.js UI
3. Precomputed summaries of full-scale datasets.

Run: .venv/bin/uvicorn api.server:app --reload --port 8000 (from repo root)
"""
import json
import logging
import pickle
import time
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("proteus.api")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PKL = ROOT / "results" / "results.pkl"
DATASETS_CACHE = Path(__file__).resolve().parent / "cache" / "datasets_summary.json"
MODELS_DIR = ROOT / "models"
MODEL_PATH = MODELS_DIR / "baseline_rf.joblib"
SCHEMA_PATH = MODELS_DIR / "feature_schema.json"
ENCODER_PATH = MODELS_DIR / "label_encoder.json"
MANIFEST_PATH = MODELS_DIR / "manifest.json"

VERSION = "1.0.0"
APP_START_TIME = time.time()

app = FastAPI(
    title="Proteus SDN-IDS API",
    version=VERSION,
    description="Drift-Aware, GAN-Augmented Intrusion Detection System API & Research Dashboard Server",
)

# CORS setup for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Internal caches
_results_cache = {"mtime": None, "data": None}
_model_cache = {
    "clf": None,
    "schema": None,
    "encoder": None,
    "manifest": None,
    "loaded": False,
}

# Operational Metrics Tracker
_metrics = {
    "total_requests": 0,
    "prediction_requests": 0,
    "total_prediction_samples": 0,
    "prediction_errors": 0,
    "latency_sum_ms": 0.0,
    "predicted_classes": {},
}


ACTIVE_RELEASE_PATH = MODELS_DIR / "active_release.json"

def _load_model_artifacts(force_reload: bool = False):
    if _model_cache["loaded"] and not force_reload:
        return _model_cache
    
    # Determine target directory
    target_model_file = MODEL_PATH
    target_schema_file = SCHEMA_PATH
    target_encoder_file = ENCODER_PATH
    target_manifest_file = MANIFEST_PATH
    release_version = "v001"

    if ACTIVE_RELEASE_PATH.exists():
        try:
            with open(ACTIVE_RELEASE_PATH, "r") as f:
                active_meta = json.load(f)
            rel_path = ROOT / active_meta.get("release_path", "models")
            if rel_path.exists():
                candidate_model = rel_path / "model.joblib"
                if candidate_model.exists():
                    target_model_file = candidate_model
                    target_schema_file = rel_path / "feature_schema.json"
                    target_encoder_file = rel_path / "label_encoder.json"
                    target_manifest_file = rel_path / "manifest.json"
                    release_version = active_meta.get("active_version", release_version)
        except Exception as e:
            log.warning(f"Could not parse active_release.json, falling back to default model: {e}")

    if target_model_file.exists() and target_schema_file.exists():
        try:
            log.info(f"Loading model artifact from {target_model_file} (release: {release_version})...")
            _model_cache["clf"] = joblib.load(target_model_file)
            with open(target_schema_file, "r") as f:
                _model_cache["schema"] = json.load(f)
            if target_manifest_file.exists():
                with open(target_manifest_file, "r") as f:
                    _model_cache["manifest"] = json.load(f)
            else:
                _model_cache["manifest"] = {"version": release_version, "model_type": type(_model_cache["clf"]).__name__}
            if target_encoder_file.exists():
                with open(target_encoder_file, "r") as f:
                    _model_cache["encoder"] = json.load(f)
            _model_cache["release_version"] = release_version
            _model_cache["loaded"] = True
            log.info(f"Model release {release_version} loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load model artifacts: {e}")
            _model_cache["loaded"] = False
    return _model_cache


# Initial load attempt
_load_model_artifacts()


def _load_results() -> Optional[dict]:
    if not RESULTS_PKL.exists():
        return None
    mtime = RESULTS_PKL.stat().st_mtime
    if _results_cache["mtime"] != mtime:
        try:
            with open(RESULTS_PKL, "rb") as f:
                _results_cache["data"] = pickle.load(f)
            _results_cache["mtime"] = mtime
        except Exception as e:
            log.error(f"Error reading results.pkl: {e}")
            return None
    return _results_cache["data"]


def _not_available(reason: str):
    return {"available": False, "reason": reason}


# ==========================================
# Pydantic Schemas for Inference
# ==========================================
class PredictionRequest(BaseModel):
    features: Union[List[float], List[List[float]], Dict[str, float]] = Field(
        ...,
        description="Feature vector as float array, batch of float arrays, or dictionary mapping feature names to floats.",
    )


class SinglePredictionResult(BaseModel):
    predicted_label: str
    predicted_index: int
    probabilities: Dict[str, float]
    inference_time_ms: float


class BatchPredictionResponse(BaseModel):
    status: str
    count: int
    predictions: List[SinglePredictionResult]
    total_time_ms: float


# ==========================================
# Core Deployment & Lifecycle Endpoints
# ==========================================
@app.get("/health")
@app.get("/api/health")
def health():
    """Healthcheck endpoint reporting service liveness and component readiness."""
    _metrics["total_requests"] += 1
    d = _load_results()
    mc = _load_model_artifacts()
    return {
        "status": "ok",
        "service": "proteus-api",
        "version": VERSION,
        "release_version": mc.get("release_version", "v001"),
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "model_loaded": mc["loaded"],
        "results_available": d is not None,
        "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/version")
@app.get("/api/version")
def version():
    """Version and build metadata endpoint."""
    _metrics["total_requests"] += 1
    mc = _load_model_artifacts()
    manifest = mc.get("manifest") or {}
    return {
        "api_version": VERSION,
        "release_version": mc.get("release_version", "v001"),
        "model_version": manifest.get("version", "1.0.0"),
        "model_type": manifest.get("model_type", "None"),
        "features_count": mc["schema"]["n_features"] if mc["loaded"] else None,
        "classes_count": mc["schema"]["n_classes"] if mc["loaded"] else None,
        "python_env": "3.12",
        "architecture": "Proteus Closed-Loop SDN-IDS",
    }


@app.get("/model")
@app.get("/api/model")
def model_info():
    """Detailed model metadata, schema, and manifest."""
    _metrics["total_requests"] += 1
    mc = _load_model_artifacts()
    if not mc["loaded"]:
        return _not_available("No serialized model artifact found in models/. Run scripts/export_deployment_artifact.py.")
    return {
        "available": True,
        "manifest": mc["manifest"],
        "schema": mc["schema"],
        "encoder": mc["encoder"],
    }


@app.get("/metrics")
@app.get("/api/metrics")
def metrics(format: Optional[str] = "json"):
    """Prometheus-compatible or JSON operational telemetry metrics."""
    _metrics["total_requests"] += 1
    avg_latency = (
        _metrics["latency_sum_ms"] / _metrics["prediction_requests"]
        if _metrics["prediction_requests"] > 0
        else 0.0
    )
    
    if format == "prometheus":
        lines = [
            "# HELP proteus_http_requests_total Total HTTP requests handled.",
            "# TYPE proteus_http_requests_total counter",
            f"proteus_http_requests_total {_metrics['total_requests']}",
            "# HELP proteus_predictions_total Total inference predictions requested.",
            "# TYPE proteus_predictions_total counter",
            f"proteus_predictions_total {_metrics['total_prediction_samples']}",
            "# HELP proteus_prediction_errors_total Total inference errors.",
            "# TYPE proteus_prediction_errors_total counter",
            f"proteus_prediction_errors_total {_metrics['prediction_errors']}",
            "# HELP proteus_prediction_latency_avg_ms Average inference latency in ms.",
            "# TYPE proteus_prediction_latency_avg_ms gauge",
            f"proteus_prediction_latency_avg_ms {avg_latency:.4f}",
        ]
        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    return {
        "total_requests": _metrics["total_requests"],
        "prediction_requests": _metrics["prediction_requests"],
        "total_prediction_samples": _metrics["total_prediction_samples"],
        "prediction_errors": _metrics["prediction_errors"],
        "average_inference_latency_ms": round(avg_latency, 4),
        "class_predictions_distribution": _metrics["predicted_classes"],
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
    }


@app.post("/predict", response_model=BatchPredictionResponse)
@app.post("/api/predict", response_model=BatchPredictionResponse)
def predict(req: PredictionRequest):
    """Run online inference on one or more network flow feature vectors."""
    t0 = time.perf_counter()
    _metrics["total_requests"] += 1
    _metrics["prediction_requests"] += 1

    mc = _load_model_artifacts()
    if not mc["loaded"] or mc["clf"] is None:
        _metrics["prediction_errors"] += 1
        raise HTTPException(
            status_code=503,
            detail="Model is not loaded. Export model artifacts first with scripts/export_deployment_artifact.py.",
        )

    clf = mc["clf"]
    schema = mc["schema"]
    feature_names = schema["feature_names"]
    class_names = schema["class_names"]
    n_expected = schema["n_features"]

    # Parse and validate input
    raw_input = req.features
    if isinstance(raw_input, dict):
        # Construct feature vector based on ordered feature names
        missing = [fn for fn in feature_names if fn not in raw_input]
        if missing:
            # Check if positional array is provided under 'values'
            if "values" in raw_input and len(raw_input["values"]) == n_expected:
                X = np.array([raw_input["values"]], dtype=np.float32)
            else:
                _metrics["prediction_errors"] += 1
                raise HTTPException(
                    status_code=422,
                    detail=f"Missing required features in dict input: {missing[:5]} (expected {n_expected} features)",
                )
        else:
            X = np.array([[raw_input[fn] for fn in feature_names]], dtype=np.float32)
    elif isinstance(raw_input, list):
        if not raw_input:
            _metrics["prediction_errors"] += 1
            raise HTTPException(status_code=422, detail="Empty feature array provided.")
        if isinstance(raw_input[0], list):
            # Batch of vectors
            for i, row in enumerate(raw_input):
                if len(row) != n_expected:
                    _metrics["prediction_errors"] += 1
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {i} has {len(row)} features, expected {n_expected}.",
                    )
            X = np.array(raw_input, dtype=np.float32)
        else:
            # Single vector
            if len(raw_input) != n_expected:
                _metrics["prediction_errors"] += 1
                raise HTTPException(
                    status_code=422,
                    detail=f"Expected {n_expected} features, got {len(raw_input)}.",
                )
            X = np.array([raw_input], dtype=np.float32)
    else:
        _metrics["prediction_errors"] += 1
        raise HTTPException(status_code=422, detail="Invalid feature input format.")

    # Run inference
    try:
        preds = clf.predict(X)
        probs = clf.predict_proba(X)
    except Exception as e:
        _metrics["prediction_errors"] += 1
        log.error(f"Inference execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    total_time_ms = (time.perf_counter() - t0) * 1000.0
    per_item_time = total_time_ms / len(X)
    _metrics["latency_sum_ms"] += total_time_ms
    _metrics["total_prediction_samples"] += len(X)

    results = []
    for pred_idx, prob_row in zip(preds, probs):
        pred_label = class_names[pred_idx] if pred_idx < len(class_names) else str(pred_idx)
        _metrics["predicted_classes"][pred_label] = _metrics["predicted_classes"].get(pred_label, 0) + 1
        prob_dict = {class_names[i]: float(p) for i, p in enumerate(prob_row)}
        results.append(
            SinglePredictionResult(
                predicted_label=pred_label,
                predicted_index=int(pred_idx),
                probabilities=prob_dict,
                inference_time_ms=round(per_item_time, 4),
            )
        )

    return BatchPredictionResponse(
        status="success",
        count=len(results),
        predictions=results,
        total_time_ms=round(total_time_ms, 3),
    )


# ==========================================
# Research Results & Dashboard Endpoints
# ==========================================
@app.get("/api/experiments/latest")
def experiments_latest():
    """Top-level summary of the most recent experiment run."""
    _metrics["total_requests"] += 1
    d = _load_results()
    if d is None:
        return _not_available("No results/results.pkl found. Run `python run_pipeline.py`.")
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
    """Per-timestep macro-F1 and per-class F1 for all conditions."""
    _metrics["total_requests"] += 1
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
    """Final held-out classification report per condition."""
    _metrics["total_requests"] += 1
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {"available": True, "class_names": d["class_names"], "final_reports": d["final_reports"]}


@app.get("/api/drift/events")
def drift_events():
    """KS-test drift detector firing log."""
    _metrics["total_requests"] += 1
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
    """WGAN-GP loss log."""
    _metrics["total_requests"] += 1
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
    """Fidelity-gate (MMD) admission log."""
    _metrics["total_requests"] += 1
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
    """Closed-loop retrain events."""
    _metrics["total_requests"] += 1
    d = _load_results()
    if d is None:
        return _not_available("No experiment run available.")
    return {"available": True, "retrain_events": d["retrain_events"]}


@app.get("/api/metrics/final")
def metrics_final():
    """Baseline classifier final held-out eval."""
    _metrics["total_requests"] += 1
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
    """SDN topology and OpenFlow telemetry connection status."""
    _metrics["total_requests"] += 1
    return _not_available(
        "Live SDN controller not connected in current mode. OpenFlow 1.3 telemetry stream requires root privileges."
    )


@app.get("/api/datasets/summary")
def datasets_summary():
    """Precomputed full-scale dataset summaries."""
    _metrics["total_requests"] += 1
    if not DATASETS_CACHE.exists():
        return _not_available(
            "Dataset summary not precomputed yet. Run `.venv/bin/python api/precompute_datasets.py`."
        )
    return {"available": True, **json.loads(DATASETS_CACHE.read_text())}


@app.get("/api/models")
def models_info():
    """Model information endpoint."""
    _metrics["total_requests"] += 1
    mc = _load_model_artifacts()
    d = _load_results()
    return {
        "deployed_model": mc["manifest"] if mc["loaded"] else None,
        "demo_results": {
            "data_source": d["data_source"] if d else None,
            "conditions": list(d["conditions"].keys()) if d else None,
        },
        "insdn_model": _not_available("InSDN model training pending credentials."),
    }
