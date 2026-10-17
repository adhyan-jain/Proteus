"""Proteus local JSON API & Online Inference Service.

Serves:
1. Production inference endpoints (/predict, /model, /health, /version, /metrics)
2. Autonomous lifecycle & drift observability endpoints (/api/drift/..., /api/lifecycle/..., /api/canary/...)
3. Research results endpoints (/api/experiments/..., /api/gate/...) for the Next.js UI
4. Precomputed summaries of full-scale datasets.

Run: .venv/bin/uvicorn api.server:app --reload --port 8000 (from repo root)
"""
from contextlib import asynccontextmanager
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

from proteus.drift_daemon import AutonomousDriftWorker, LiveSampleBuffer
from proteus.model_manager import ModelBundle, ModelManager
from proteus.release_manager import rollback_release

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("proteus.api")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PKL = ROOT / "results" / "results.pkl"
DATASETS_CACHE = Path(__file__).resolve().parent / "cache" / "datasets_summary.json"
MODELS_DIR = ROOT / "models"
ACTIVE_RELEASE_PATH = MODELS_DIR / "active_release.json"

VERSION = "1.0.0"
APP_START_TIME = time.time()

# Core Lifecycle Singletons
model_manager = ModelManager(models_dir=MODELS_DIR)
sample_buffer = LiveSampleBuffer(maxlen=5000, reference_size=200)
drift_worker = AutonomousDriftWorker(
    sample_buffer=sample_buffer,
    model_manager=model_manager,
    models_dir=MODELS_DIR,
    check_interval_seconds=2.0,
    eval_window_size=50,
    ks_alpha=0.01,
    cooldown_seconds=3.0,
    canary_sample_count=50,
    canary_max_error_rate=0.05,
)

# Operational Metrics Tracker
_metrics = {
    "total_requests": 0,
    "prediction_requests": 0,
    "total_prediction_samples": 0,
    "prediction_errors": 0,
    "latency_sum_ms": 0.0,
    "predicted_classes": {},
}

_results_cache = {"mtime": None, "data": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan Context Manager: start & stop autonomous background daemon."""
    log.info("Starting Proteus Autonomous Drift Monitoring Daemon...")
    drift_worker.start()
    yield
    log.info("Stopping Proteus Autonomous Drift Monitoring Daemon...")
    drift_worker.stop()


app = FastAPI(
    title="Proteus SDN-IDS API",
    version=VERSION,
    description="Drift-Aware, GAN-Augmented Intrusion Detection System API & Dashboard Server",
    lifespan=lifespan,
)

from api.research import router as research_router  # noqa: E402  read-only research artifacts
app.include_router(research_router)

# CORS setup for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _load_model_artifacts(force_reload: bool = False) -> Dict[str, Any]:
    """Backward-compatible helper querying active ModelManager bundle."""
    if force_reload:
        model_manager.check_and_reload_if_updated()
    
    bundle = model_manager.get_bundle()
    if bundle is None:
        return {
            "clf": None,
            "schema": None,
            "encoder": None,
            "manifest": None,
            "release_version": "None",
            "loaded": False,
        }
    return {
        "clf": bundle.clf,
        "schema": bundle.schema,
        "encoder": bundle.encoder,
        "manifest": bundle.manifest,
        "release_version": bundle.release_version,
        "loaded": True,
    }


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
# Pydantic Schemas for Inference & Lifecycle
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


class HotSwapRequest(BaseModel):
    version: str = Field(..., description="Target release version name (e.g. v001, v002)")


class RollbackRequest(BaseModel):
    target_version: Optional[str] = Field(None, description="Optional target version to roll back to")


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
    daemon_status = drift_worker.get_status()
    return {
        "status": "ok",
        "service": "proteus-api",
        "version": VERSION,
        "release_version": mc.get("release_version", "v001"),
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "model_loaded": mc["loaded"],
        "results_available": d is not None,
        "daemon_state": daemon_status["state"],
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
        "architecture": "Proteus Closed-Loop Autonomous SDN-IDS",
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
        "release_version": mc["release_version"],
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
            "# HELP proteus_drift_triggers_total Total autonomous drift triggers.",
            "# TYPE proteus_drift_triggers_total counter",
            f"proteus_drift_triggers_total {drift_worker.total_drift_triggers}",
            "# HELP proteus_model_promotions_total Total autonomous model promotions.",
            "# TYPE proteus_model_promotions_total counter",
            f"proteus_model_promotions_total {drift_worker.total_promotions}",
            "# HELP proteus_model_rollbacks_total Total model rollbacks.",
            "# TYPE proteus_model_rollbacks_total counter",
            f"proteus_model_rollbacks_total {drift_worker.total_rollbacks}",
        ]
        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    return {
        "total_requests": _metrics["total_requests"],
        "prediction_requests": _metrics["prediction_requests"],
        "total_prediction_samples": _metrics["total_prediction_samples"],
        "prediction_errors": _metrics["prediction_errors"],
        "average_inference_latency_ms": round(avg_latency, 4),
        "class_predictions_distribution": _metrics["predicted_classes"],
        "autonomous_lifecycle": {
            "drift_triggers": drift_worker.total_drift_triggers,
            "adaptations": drift_worker.total_adaptations,
            "promotions": drift_worker.total_promotions,
            "rollbacks": drift_worker.total_rollbacks,
            "state": drift_worker.state,
        },
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
    }


@app.post("/predict", response_model=BatchPredictionResponse)
@app.post("/api/predict", response_model=BatchPredictionResponse)
def predict(req: PredictionRequest):
    """Run online inference on one or more network flow feature vectors, feed sample ring buffer, and record canary."""
    t0 = time.perf_counter()
    _metrics["total_requests"] += 1
    _metrics["prediction_requests"] += 1

    bundle: Optional[ModelBundle] = model_manager.get_bundle()
    if bundle is None or bundle.clf is None:
        _metrics["prediction_errors"] += 1
        drift_worker.record_inference_outcome(is_error=True)
        raise HTTPException(
            status_code=503,
            detail="Model is not loaded. Export model artifacts first with scripts/export_deployment_artifact.py.",
        )

    clf = bundle.clf
    schema = bundle.schema
    feature_names = bundle.feature_names
    class_names = bundle.class_names
    n_expected = bundle.n_features

    # Parse and validate input
    raw_input = req.features
    if isinstance(raw_input, dict):
        # Check if positional array is provided under 'values'
        if "values" in raw_input and len(raw_input["values"]) == n_expected:
            X = np.array([raw_input["values"]], dtype=np.float32)
        else:
            from sdn.topology.feature_mapper import map_schema_to_feature_vector
            vec = map_schema_to_feature_vector(raw_input, feature_names)
            X = np.array([vec], dtype=np.float32)

    elif isinstance(raw_input, list):
        if not raw_input:
            _metrics["prediction_errors"] += 1
            drift_worker.record_inference_outcome(is_error=True)
            raise HTTPException(status_code=422, detail="Empty feature array provided.")
        if isinstance(raw_input[0], list):
            # Batch of vectors
            for i, row in enumerate(raw_input):
                if len(row) != n_expected:
                    _metrics["prediction_errors"] += 1
                    drift_worker.record_inference_outcome(is_error=True)
                    raise HTTPException(
                        status_code=422,
                        detail=f"Row {i} has {len(row)} features, expected {n_expected}.",
                    )
            X = np.array(raw_input, dtype=np.float32)
        else:
            # Single vector
            if len(raw_input) != n_expected:
                _metrics["prediction_errors"] += 1
                drift_worker.record_inference_outcome(is_error=True)
                raise HTTPException(
                    status_code=422,
                    detail=f"Expected {n_expected} features, got {len(raw_input)}.",
                )
            X = np.array([raw_input], dtype=np.float32)
    else:
        _metrics["prediction_errors"] += 1
        drift_worker.record_inference_outcome(is_error=True)
        raise HTTPException(status_code=422, detail="Invalid feature input format.")

    # Run inference
    try:
        preds = clf.predict(X)
        probs = clf.predict_proba(X)
    except Exception as e:
        _metrics["prediction_errors"] += 1
        drift_worker.record_inference_outcome(is_error=True)
        log.error(f"Inference execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    total_time_ms = (time.perf_counter() - t0) * 1000.0
    per_item_time = total_time_ms / len(X)
    _metrics["latency_sum_ms"] += total_time_ms
    _metrics["total_prediction_samples"] += len(X)

    results = []
    for pred_idx, prob_row, feat_row in zip(preds, probs, X):
        pred_label = class_names[pred_idx] if pred_idx < len(class_names) else str(pred_idx)
        _metrics["predicted_classes"][pred_label] = _metrics["predicted_classes"].get(pred_label, 0) + 1
        confidence = float(np.max(prob_row))
        
        # Ingest into live streaming ring buffer
        sample_buffer.add(feat_row, int(pred_idx), confidence)
        # Record outcome for canary health monitor
        drift_worker.record_inference_outcome(is_error=False, confidence=confidence)

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
# Autonomous Lifecycle & Observability Endpoints
# ==========================================
@app.get("/api/drift/status")
def drift_status():
    """Live telemetry on drift monitoring buffer, state machine, and adaptation events."""
    _metrics["total_requests"] += 1
    return {
        "available": True,
        **drift_worker.get_status(),
    }


@app.post("/api/drift/trigger-check")
def drift_trigger_check():
    """Manually trigger immediate drift test against current live sample buffer."""
    _metrics["total_requests"] += 1
    res = drift_worker.trigger_manual_check()
    return {"status": "ok", "result": res}


@app.get("/api/lifecycle/history")
def lifecycle_history():
    """Complete lifecycle event log for drift, adaptation, release promotion, and rollback."""
    _metrics["total_requests"] += 1
    return {
        "available": True,
        "active_release": model_manager.get_bundle().release_version if model_manager.get_bundle() else None,
        "total_drift_triggers": drift_worker.total_drift_triggers,
        "total_adaptations": drift_worker.total_adaptations,
        "total_promotions": drift_worker.total_promotions,
        "total_rollbacks": drift_worker.total_rollbacks,
        "last_drift_event": drift_worker.last_drift_event,
        "last_adaptation_event": drift_worker.last_adaptation_event,
        "last_promotion_event": drift_worker.last_promotion_event,
        "last_rollback_event": drift_worker.last_rollback_event,
    }


@app.get("/api/canary/status")
def canary_status():
    """Status of post-deployment canary monitor."""
    _metrics["total_requests"] += 1
    status = drift_worker.get_status()
    return {
        "available": True,
        "canary": status["canary_monitoring"],
        "state": status["state"],
        "active_version": status["active_version"],
    }


@app.post("/api/model/hot-swap/{version}")
def hot_swap_model(version: str):
    """Trigger zero-downtime in-memory model hot-swap to target release version."""
    _metrics["total_requests"] += 1
    try:
        bundle = model_manager.hot_swap_to_release(version, promote_on_disk=True)
        return {
            "status": "success",
            "message": f"Successfully hot-swapped in-memory model to release {version}",
            "active_version": bundle.release_version,
            "loaded_at": bundle.loaded_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Hot-swap failed: {str(e)}")


@app.post("/api/model/rollback")
def rollback_model_endpoint(req: Optional[RollbackRequest] = None):
    """Trigger zero-downtime rollback to previous or specified release version."""
    _metrics["total_requests"] += 1
    target = req.target_version if req else None
    try:
        active_ver, rolled_back_to = rollback_release(models_dir=MODELS_DIR, target_version=target)
        bundle = model_manager.hot_swap_to_release(rolled_back_to, promote_on_disk=True)
        return {
            "status": "success",
            "message": f"Rolled back from {active_ver} -> {rolled_back_to}",
            "active_version": bundle.release_version,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Rollback failed: {str(e)}")


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
    return {
        "available": True,
        "controller": "Ryu 4.34 OpenFlow 1.3",
        "ids_app": "sdn/topology/ryu_ids_app.py",
        "inference_bridge": "Async HTTP POST -> http://localhost:8000/predict",
        "resilience": "Non-blocking event loop with fail-open circuit-breaker fallback",
    }


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
        "active_release": mc["release_version"],
        "demo_results": {
            "data_source": d["data_source"] if d else None,
            "conditions": list(d["conditions"].keys()) if d else None,
        },
        "insdn_model": _not_available("InSDN model training pending credentials."),
    }
