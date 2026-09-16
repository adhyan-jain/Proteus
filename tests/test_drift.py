"""Behavioral tests for the KS-test drift detector (proteus/drift.py)."""
import numpy as np

from proteus.drift import detect_drift


def test_no_drift_when_distributions_match():
    rng = np.random.default_rng(1)
    ref = rng.uniform(0.5, 1.0, size=1000)
    cur = rng.uniform(0.5, 1.0, size=1000)
    result = detect_drift(cur, ref, alpha=0.05)
    assert result["fired"] is False
    assert result["p_value"] >= 0.05


def test_drift_fires_for_clearly_shifted_distribution():
    rng = np.random.default_rng(1)
    ref = rng.uniform(0.8, 1.0, size=1000)   # high-confidence predictions
    cur = rng.uniform(0.1, 0.4, size=1000)   # much lower confidence -- real distribution shift
    result = detect_drift(cur, ref, alpha=0.05)
    assert result["fired"] is True
    assert result["p_value"] < 0.05


def test_alpha_threshold_is_respected_in_output():
    rng = np.random.default_rng(2)
    ref = rng.normal(size=500)
    cur = rng.normal(size=500)
    result = detect_drift(cur, ref, alpha=0.01)
    assert result["alpha"] == 0.01


def test_detector_is_symmetric_in_which_side_is_reference():
    """The KS statistic must not depend on argument order (only p-value/statistic values,
    not which sample is labeled 'reference' vs 'current')."""
    rng = np.random.default_rng(3)
    a = rng.normal(size=300)
    b = rng.normal(loc=3.0, size=300)
    r1 = detect_drift(a, b)
    r2 = detect_drift(b, a)
    assert r1["statistic"] == r2["statistic"]
    assert r1["fired"] == r2["fired"]
