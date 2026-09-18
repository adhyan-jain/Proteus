"""Unit tests for post-deployment canary evaluation and automated failure rollback."""
from pathlib import Path
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from proteus.drift_daemon import AutonomousDriftWorker, LiveSampleBuffer
from proteus.model_manager import ModelManager
from proteus.release_manager import get_active_release, package_release


def test_canary_failure_triggers_automatic_rollback(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    feature_names = ["f1", "f2", "f3", "f4"]
    class_names = ["benign", "malicious"]

    # v001 base
    clf1 = RandomForestClassifier(n_estimators=5, random_state=42)
    clf1.fit(np.random.randn(20, 4), np.random.choice([0, 1], size=20))
    package_release(clf1, feature_names, class_names, "v001", {}, models_dir, promote=True)

    # v002 candidate
    clf2 = RandomForestClassifier(n_estimators=5, random_state=42)
    clf2.fit(np.random.randn(20, 4), np.random.choice([0, 1], size=20))
    package_release(clf2, feature_names, class_names, "v002", {}, models_dir, promote=False)

    mgr = ModelManager(models_dir=models_dir)
    buf = LiveSampleBuffer(maxlen=100)

    worker = AutonomousDriftWorker(
        sample_buffer=buf,
        model_manager=mgr,
        models_dir=models_dir,
        canary_sample_count=10,
        canary_max_error_rate=0.10,
    )

    # Manually promote v002 to test canary
    mgr.hot_swap_to_release("v002", promote_on_disk=True)
    worker._canary_active = True
    worker._canary_promoted_version = "v002"
    worker._canary_previous_version = "v001"
    worker._canary_errors = 0
    worker._canary_samples_evaluated = 0
    worker.state = "CANARY_MONITORING"

    assert mgr.get_bundle().release_version == "v002"

    # Simulate 10 live predictions with 5 errors (50% error rate > 10% threshold)
    for i in range(10):
        worker.record_inference_outcome(is_error=(i % 2 == 0), confidence=0.05 if i % 2 == 0 else 0.95)

    # Trigger canary evaluation
    worker._evaluate_canary_health()

    # Verify automated rollback occurred
    assert mgr.get_bundle().release_version == "v001"
    assert get_active_release(models_dir)["active_version"] == "v001"
    status = worker.get_status()
    assert status["total_rollbacks"] == 1
    assert status["last_rollback_event"]["target_version"] == "v001"
    assert status["last_rollback_event"]["rolled_back_from"] == "v002"
