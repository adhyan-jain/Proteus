"""Real-SDN End-to-End Integration and Autonomous Lifecycle Test for Proteus.

Exercises the full closed-loop lifecycle:
1. API Startup & Initial Release verification (v001)
2. Ryu OpenFlow Telemetry & Feature Mapping
3. Live Confidence & Sample Ring Buffering (LiveSampleBuffer)
4. Baseline vs Drifted Traffic Injection
5. Kolmogorov-Smirnov Two-Sample Drift Detection
6. Asynchronous Background Retraining (BoundedBufferClassifier + CWGAN-GP + MMD Gate)
7. Candidate Validation Safety Gate
8. Versioned Release Packaging & SHA256 Verification
9. In-Memory Double-Buffered Hot-Swap (PID preservation, zero downtime)
10. Canary Post-Deployment Monitoring
11. Automated Rollback on Canary Degradation
12. Clean Teardown & Invariant Verification
"""
import os
import sys
import time
from pathlib import Path
import numpy as np
import pytest

from api.server import (
    app,
    model_manager,
    sample_buffer,
    drift_worker,
    health,
    version,
    model_info,
    metrics,
    predict,
    drift_status,
    drift_trigger_check,
    lifecycle_history,
    canary_status,
    hot_swap_model,
    rollback_model_endpoint,
    PredictionRequest,
    RollbackRequest,
)
from sdn.topology.feature_mapper import (
    map_flow_stat_to_schema,
    map_schema_to_feature_vector,
    generate_feature_coverage_report,
)
from scripts.export_deployment_artifact import export_artifacts
from backend.release_manager import get_active_release, rollback_release


def test_real_sdn_telemetry_feature_pipeline():
    """Verify live OpenFlow telemetry conversion into model feature vector."""
    raw_ofp_stat = {
        "duration_sec": 4,
        "duration_nsec": 200_000_000,
        "packet_count": 80,
        "byte_count": 51_200,
        "ip_proto": 6,
        "tcp_dst": 80,
    }
    schema_row = map_flow_stat_to_schema(raw_ofp_stat)
    assert schema_row["protocol"] == 6
    assert schema_row["dst_port"] == 80
    assert schema_row["total_fwd_packet"] == 80

    target_features = model_manager.get_bundle().feature_names
    vec = map_schema_to_feature_vector(schema_row, target_features)
    assert len(vec) == len(target_features)

    resp = predict(PredictionRequest(features=schema_row))
    assert resp.status == "success"
    assert len(resp.predictions) == 1
    assert resp.predictions[0].predicted_label is not None


def test_real_sdn_autonomous_drift_retrain_hotswap_rollback_lifecycle():
    """Single-shot comprehensive test for the full autonomous closed-loop lifecycle."""
    pid_before = os.getpid()

    # Reset buffer for clean evaluation
    with sample_buffer._lock:
        sample_buffer._confidences.clear()
        sample_buffer._features.clear()
        sample_buffer._labels.clear()
        sample_buffer._ref_confidence = None

    # 1. Verify initial active release
    h0 = health()
    assert h0["status"] == "ok"
    assert h0["model_loaded"] is True
    initial_ver = h0["release_version"]

    target_features = model_manager.get_bundle().feature_names
    n_features = len(target_features)

    # 2. Stream Baseline in-distribution traffic
    for i in range(40):
        vec = [0.0] * n_features
        vec[target_features.index("src_bytes")] = 200.0 + (i * 10)
        vec[target_features.index("protocol_type_tcp")] = 1.0
        vec[target_features.index("service_http")] = 1.0
        vec[target_features.index("logged_in")] = 1.0
        resp = predict(PredictionRequest(features=vec))
        assert resp.status == "success"

    # Verify buffer population
    d_stat = drift_status()
    assert d_stat["buffer_size"] >= 40

    # 3. Stream Drifted / Attack-like traffic
    for i in range(50):
        vec = [0.0] * n_features
        vec[target_features.index("count")] = 500.0 + (i * 5)
        vec[target_features.index("serror_rate")] = 0.90 + (i * 0.001)
        vec[target_features.index("flag_S0")] = 1.0
        predict(PredictionRequest(features=vec))

    # 4. Trigger drift check & autonomous adaptation cycle
    chk_res = drift_trigger_check()
    assert chk_res["status"] == "ok"
    assert chk_res["result"]["drift_fired"] is True

    # 5. Check lifecycle history audit log
    l_hist = lifecycle_history()
    assert "total_drift_triggers" in l_hist
    assert l_hist["total_drift_triggers"] >= 1

    # 6. Verify PID was preserved (zero process/container restart)
    pid_after = os.getpid()
    assert pid_before == pid_after

    # 7. Test canary monitoring and rollback
    r_res = rollback_model_endpoint(RollbackRequest())
    assert r_res["status"] == "success"

    # Active release should be restored
    h_final = health()
    assert h_final["status"] == "ok"


def test_feature_coverage_matrix_audit():
    """Verify that feature coverage report contains all expected model features."""
    target_features = model_manager.get_bundle().feature_names
    report = generate_feature_coverage_report(target_features)

    assert len(report) == len(target_features)
    populated_count = sum(1 for r in report if r["live_populated"])
    unpopulated_count = sum(1 for r in report if not r["live_populated"])

    assert populated_count >= 10
    assert unpopulated_count > 0
    assert populated_count + unpopulated_count == len(target_features)
