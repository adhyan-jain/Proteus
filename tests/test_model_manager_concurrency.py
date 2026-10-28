"""Concurrent inference & zero-downtime model hot-swapping tests."""
import concurrent.futures
import threading
import time
from pathlib import Path
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from backend.model_manager import ModelManager
from backend.release_manager import package_release


@pytest.fixture
def models_setup(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Train v001 model with both classes
    clf1 = RandomForestClassifier(n_estimators=5, random_state=42)
    X1 = np.random.randn(50, 4).astype(np.float32)
    y1 = np.array([0, 1] * 25, dtype=np.int64)
    clf1.fit(X1, y1)
    package_release(clf1, ["f1", "f2", "f3", "f4"], ["normal", "anomaly"], "v001", {}, models_dir, promote=True)

    # Train v002 model with both classes
    clf2 = RandomForestClassifier(n_estimators=5, random_state=42)
    X2 = np.random.randn(50, 4).astype(np.float32)
    y2 = np.array([0, 1] * 25, dtype=np.int64)
    clf2.fit(X2, y2)
    package_release(clf2, ["f1", "f2", "f3", "f4"], ["normal", "anomaly"], "v002", {}, models_dir, promote=False)

    return models_dir


def test_concurrent_hot_swap_zero_downtime(models_setup):
    """Verify that multiple client threads running predictions encounter 0 exceptions while hot swap occurs."""
    models_dir = models_setup
    mgr = ModelManager(models_dir=models_dir)

    initial_bundle = mgr.get_bundle()
    assert initial_bundle is not None
    assert initial_bundle.release_version == "v001"

    stop_event = threading.Event()
    num_threads = 8
    success_count = [0] * num_threads
    errors = []

    def worker(worker_id: int):
        X = np.random.randn(2, 4).astype(np.float32)
        while not stop_event.is_set():
            try:
                bundle = mgr.get_bundle()
                assert bundle is not None
                preds = bundle.predict(X)
                probs = bundle.predict_proba(X)
                assert len(preds) == 2
                assert probs.shape == (2, 2)
                success_count[worker_id] += 1
            except Exception as e:
                errors.append(str(e))
            time.sleep(0.001)

    # Launch concurrent readers
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)

    # Let workers run for a bit
    time.sleep(0.1)

    # Trigger hot-swap to v002
    new_bundle = mgr.hot_swap_to_release("v002", promote_on_disk=True)
    assert new_bundle.release_version == "v002"

    # Allow workers to continue on the new model
    time.sleep(0.2)
    stop_event.set()

    for t in threads:
        t.join(timeout=2.0)

    total_successes = sum(success_count)
    total_errors = len(errors)

    assert total_successes > 100
    assert total_errors == 0, f"Encountered {total_errors} prediction failures during live hot-swap: {errors[:3]}"
    assert mgr.get_bundle().release_version == "v002"
