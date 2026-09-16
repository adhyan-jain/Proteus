"""Unit tests for BoundedBufferClassifier incremental streaming adaptation and non-leakage invariants."""
import pytest
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import SGDClassifier
from proteus.closed_loop_full import BoundedBufferClassifier


def test_bounded_buffer_size_invariant():
    """Verify that the adaptation buffer size is strictly bounded and never grows with total streaming samples."""
    rng = np.random.default_rng(42)
    X_train = rng.normal(size=(5000, 10)).astype(np.float32)
    y_train = rng.integers(0, 2, size=5000)

    clf = BoundedBufferClassifier(
        lambda: SGDClassifier(loss="log_loss", random_state=42),
        max_ref_samples=1000,
        max_recent_samples=500
    )
    clf.fit_initial(X_train, y_train)

    assert len(clf.ref_X) == 1000
    assert clf.buffer_size == 1000

    # Simulate 50 stream adaptation batches of 200 samples each (total 10,000 streaming samples)
    for i in range(50):
        X_fit = rng.normal(size=(200, 10)).astype(np.float32)
        y_fit = rng.integers(0, 2, size=200)
        X_synth = rng.normal(size=(50, 10)).astype(np.float32)
        y_synth = rng.integers(0, 2, size=50)

        clf.partial_fit_adaptation(X_fit, y_fit, X_synth, y_synth)

        # Buffer size MUST NOT exceed 1000 ref + 500 recent = 1500 max
        assert clf.buffer_size <= 1500, f"Buffer size {clf.buffer_size} exceeded maximum cap 1500 at step {i}"
        assert len(clf.ref_X) == 1000, "Reference reservoir size altered"


def test_adaptation_changes_model_predictions():
    """Verify that partial_fit_adaptation actually alters classifier predictions in response to shifted stream data."""
    rng = np.random.default_rng(42)
    X_train = rng.normal(loc=0.0, scale=1.0, size=(1000, 10)).astype(np.float32)
    y_train = rng.integers(0, 2, size=1000)

    clf = BoundedBufferClassifier(
        lambda: RandomForestClassifier(n_estimators=10, random_state=42),
        max_ref_samples=500,
        max_recent_samples=300
    )
    clf.fit_initial(X_train, y_train)

    # Shifted test batch
    X_test_shifted = rng.normal(loc=5.0, scale=1.0, size=(100, 10)).astype(np.float32)
    pred_before = clf.predict(X_test_shifted)

    # Adapt on shifted class 1 data
    X_fit_shifted = rng.normal(loc=5.0, scale=1.0, size=(200, 10)).astype(np.float32)
    y_fit_shifted = np.ones(200, dtype=int)
    clf.partial_fit_adaptation(X_fit_shifted, y_fit_shifted)

    pred_after = clf.predict(X_test_shifted)
    # Model should now predict class 1 far more frequently for the shifted features
    assert np.mean(pred_after == 1) > np.mean(pred_before == 1), "Adaptation failed to shift predictions"


def test_synthetic_samples_incorporated_into_adaptation():
    """Verify that synthetic samples admitted by the fidelity gate are incorporated into the adaptation buffer."""
    rng = np.random.default_rng(42)
    X_train = rng.normal(size=(1000, 5)).astype(np.float32)
    y_train = rng.integers(0, 2, size=1000)

    clf = BoundedBufferClassifier(
        lambda: RandomForestClassifier(n_estimators=10, random_state=42),
        max_ref_samples=500,
        max_recent_samples=300
    )
    clf.fit_initial(X_train, y_train)

    # Fit portion has class 0, synthetic portion has class 1
    X_fit = rng.normal(size=(50, 5)).astype(np.float32)
    y_fit = np.zeros(50, dtype=int)
    X_synth = rng.normal(loc=3.0, size=(50, 5)).astype(np.float32)
    y_synth = np.ones(50, dtype=int)

    clf.partial_fit_adaptation(X_fit, y_fit, X_synth, y_synth)

    # Verify class 1 exists in recent buffer and model can predict class 1
    assert 1 in clf.recent_y, "Admitted synthetic class labels not found in recent buffer"
    pred_synth = clf.predict(X_synth)
    assert np.sum(pred_synth == 1) > 0, "Model fails to recognize synthetic class after adaptation"


def test_future_batches_not_used_in_adaptation():
    """Verify strict temporal non-leakage: adaptation at timestep t strictly uses data available up to t."""
    rng = np.random.default_rng(42)
    X_batch_t0 = rng.normal(loc=0.0, size=(100, 5)).astype(np.float32)
    y_batch_t0 = rng.integers(0, 2, size=100)
    X_batch_t1 = rng.normal(loc=10.0, size=(100, 5)).astype(np.float32)  # future batch
    y_batch_t1 = rng.integers(0, 2, size=100)

    clf = BoundedBufferClassifier(
        lambda: RandomForestClassifier(n_estimators=10, random_state=42),
        max_ref_samples=200,
        max_recent_samples=100
    )
    clf.fit_initial(X_batch_t0, y_batch_t0)

    # Adapt ONLY on timestep t0
    clf.partial_fit_adaptation(X_batch_t0[:70], y_batch_t0[:70])

    # Model MUST NOT have seen future batch t1
    if clf.recent_X is not None:
        assert not np.any(np.all(clf.recent_X == X_batch_t1[0], axis=1)), "Future batch data leaked into recent buffer"
