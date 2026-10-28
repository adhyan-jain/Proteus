"""Unit and integration tests for autonomous drift detection and background retraining daemon."""
import time
from pathlib import Path
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from backend.drift_daemon import (
    AutonomousDriftWorker,
    CandidateValidationGate,
    LiveSampleBuffer,
)
from backend.model_manager import ModelManager
from backend.release_manager import package_release


def test_live_sample_buffer():
    buf = LiveSampleBuffer(maxlen=100, reference_size=10)
    assert buf.size() == 0

    # Add 10 baseline samples
    for _ in range(10):
        buf.add(np.array([1.0, 2.0]), predicted_label=0, confidence=0.95)

    assert buf.size() == 10
    ref_conf = buf.get_reference_confidence()
    assert ref_conf is not None
    assert len(ref_conf) == 10

    # Add 20 more samples
    for _ in range(20):
        buf.add(np.array([1.0, 2.0]), predicted_label=1, confidence=0.50)

    assert buf.size() == 30
    recent = buf.get_recent_confidences(n=15)
    assert len(recent) == 15
    assert np.allclose(recent, 0.50)

    X_rec, y_rec = buf.get_recent_samples(n=5)
    assert X_rec.shape == (5, 2)
    assert len(y_rec) == 5


def test_candidate_validation_gate():
    # Synthetic validation data
    X_val = np.random.randn(20, 4).astype(np.float32)
    y_val = np.random.choice([0, 1], size=20)
    gate = CandidateValidationGate(baseline_validation_data=(X_val, y_val))

    feature_names = ["f1", "f2", "f3", "f4"]
    class_names = ["c0", "c1"]

    # Valid classifier
    clf_good = RandomForestClassifier(n_estimators=5, random_state=42)
    clf_good.fit(X_val, y_val)

    passed, reason, metrics = gate.validate_candidate(clf_good, feature_names, class_names)
    assert passed is True
    assert metrics["validation_passed"] is True
    assert "validation_accuracy" in metrics


def test_autonomous_worker_full_adaptation_cycle(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    feature_names = ["f1", "f2", "f3", "f4"]
    class_names = ["benign", "malicious"]
    n_features = 4

    # 1. Base model
    clf_base = RandomForestClassifier(n_estimators=5, random_state=42)
    X_init = np.random.randn(50, n_features).astype(np.float32)
    y_init = np.random.choice([0, 1], size=50)
    clf_base.fit(X_init, y_init)

    package_release(clf_base, feature_names, class_names, "v001", {}, models_dir, promote=True)

    mgr = ModelManager(models_dir=models_dir)
    assert mgr.get_bundle().release_version == "v001"

    buf = LiveSampleBuffer(maxlen=500, reference_size=30)
    # Calibrate reference window with high confidence
    for _ in range(30):
        feat = np.random.randn(n_features).astype(np.float32)
        buf.add(feat, predicted_label=0, confidence=0.98)

    worker = AutonomousDriftWorker(
        sample_buffer=buf,
        model_manager=mgr,
        models_dir=models_dir,
        check_interval_seconds=0.2,
        eval_window_size=30,
        ks_alpha=0.05,
        cooldown_seconds=0.1,
    )

    # 2. Inject drifted samples (drastically reduced confidence + shifted distribution)
    for _ in range(35):
        feat = np.random.randn(n_features).astype(np.float32) + 5.0
        buf.add(feat, predicted_label=1, confidence=0.20)

    # Execute adaptation cycle directly
    worker._check_drift_and_adapt_if_needed()

    # Wait for off-path executor to finish adaptation
    for _ in range(50):
        if mgr.get_bundle().release_version == "v002":
            break
        time.sleep(0.1)

    assert mgr.get_bundle().release_version == "v002"
    status = worker.get_status()
    assert status["total_drift_triggers"] >= 1
    assert status["total_promotions"] >= 1
    assert status["last_promotion_event"]["promoted_version"] == "v002"
