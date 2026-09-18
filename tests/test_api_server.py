"""Direct unit tests for API endpoints and inference functions without external HTTP client dependencies."""
import pytest
from api.server import (
    health,
    version,
    model_info,
    metrics,
    predict,
    PredictionRequest,
)

def test_health_endpoint():
    res = health()
    assert res["status"] == "ok"
    assert res["service"] == "proteus-api"
    assert "version" in res
    assert "model_loaded" in res

def test_version_endpoint():
    res = version()
    assert "api_version" in res
    assert "model_version" in res
    assert res["python_env"] == "3.12"
    assert "Proteus Closed-Loop" in res["architecture"]

def test_model_endpoint():
    res = model_info()
    if res.get("available"):
        assert "manifest" in res
        assert "schema" in res
        assert res["schema"]["n_features"] > 0
        assert res["schema"]["n_classes"] > 0

def test_metrics_endpoints():
    # JSON format
    m_json = metrics(format="json")
    assert "total_requests" in m_json
    assert "prediction_requests" in m_json
    assert "uptime_seconds" in m_json

    # Prometheus format
    m_prom = metrics(format="prometheus")
    assert "proteus_http_requests_total" in m_prom.body.decode()

def test_predict_functionality():
    m = model_info()
    if not m.get("available"):
        pytest.skip("Model artifact not available")
    
    n_features = m["schema"]["n_features"]
    
    # 1. Single sample prediction
    req_single = PredictionRequest(features=[0.5] * n_features)
    resp_single = predict(req_single)
    assert resp_single.status == "success"
    assert resp_single.count == 1
    assert len(resp_single.predictions) == 1
    assert isinstance(resp_single.predictions[0].predicted_label, str)
    assert len(resp_single.predictions[0].probabilities) == m["schema"]["n_classes"]

    # 2. Batch sample prediction
    req_batch = PredictionRequest(features=[[0.1] * n_features, [1.0] * n_features])
    resp_batch = predict(req_batch)
    assert resp_batch.status == "success"
    assert resp_batch.count == 2
    assert len(resp_batch.predictions) == 2

    # 3. Invalid dimension handling
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        predict(PredictionRequest(features=[1.0, 2.0]))
    assert exc_info.value.status_code == 422
