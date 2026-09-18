"""Full end-to-end integration test for the autonomous closed-loop SDN-IDS lifecycle."""
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
from scripts.export_deployment_artifact import export_artifacts


def test_complete_autonomous_lifecycle():
    # 1. Verify initial health & version
    h = health()
    assert h["status"] == "ok"
    assert h["model_loaded"] is True
    initial_version = h["release_version"]

    # 2. Query model metadata
    mdata = model_info()
    assert mdata["available"] is True
    feature_names = mdata["schema"]["feature_names"]
    n_features = len(feature_names)

    # 3. Stream baseline in-distribution samples to calibrate buffer
    for _ in range(40):
        req = PredictionRequest(features=[0.5] * n_features)
        resp = predict(req)
        assert resp.status == "success"
        assert len(resp.predictions) == 1

    # Check drift status
    dstatus = drift_status()
    assert dstatus["buffer_size"] >= 40

    # 4. Stream drifted samples to trigger autonomous adaptation
    for _ in range(50):
        req = PredictionRequest(features=[10.0] * n_features)
        predict(req)

    # Trigger drift check
    r_chk = drift_trigger_check()
    assert r_chk["status"] == "ok"

    # 5. Check lifecycle history endpoint
    ldata = lifecycle_history()
    assert "total_drift_triggers" in ldata

    # 6. Check canary status
    cstatus = canary_status()
    assert "canary" in cstatus

    # 7. Test manual hot-swap endpoint
    r_swap = hot_swap_model(version=initial_version)
    assert r_swap["status"] == "success"
    assert r_swap["active_version"] == initial_version

    # 8. Test metrics endpoint
    m_prom = metrics(format="prometheus")
    assert "proteus_predictions_total" in m_prom.body.decode()
