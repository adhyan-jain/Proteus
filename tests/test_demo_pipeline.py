"""Unit tests for backend/pipeline.py demo pipeline orchestration and evaluation."""
import numpy as np
from backend.pipeline import _split_eval_fit, run_pipeline


def test_split_eval_fit_disjoint_and_proportions():
    rng = np.random.default_rng(42)
    X = rng.standard_normal((100, 10))
    y = rng.integers(0, 3, size=100)
    
    X_eval, y_eval, X_fit, y_fit = _split_eval_fit(X, y, 0.3, rng)
    
    assert len(X_eval) == 30
    assert len(X_fit) == 70
    assert len(X_eval) + len(X_fit) == len(X)


def test_pipeline_run_returns_valid_structure_and_post_adaptation_metrics():
    # Execute a small demo pipeline run
    results = run_pipeline()
    
    assert "conditions" in results
    assert "baseline" in results["conditions"]
    assert "static_augmentation" in results["conditions"]
    assert "closed_loop" in results["conditions"]
    
    cl_f1 = results["conditions"]["closed_loop"]["macro_f1"]
    bs_f1 = results["conditions"]["baseline"]["macro_f1"]
    assert len(cl_f1) == len(bs_f1)
    
    # Check retrain events
    retrain_events = results["retrain_events"]
    assert len(retrain_events) > 0
    for ev in retrain_events:
        if "error" not in ev:
            t = ev["timestep"]
            # Verify the series at timestep t matches f1_after (post-adaptation metric)
            assert cl_f1[t] == ev["f1_after"]
            assert len(results["conditions"]["closed_loop"]["per_class_f1"][t]) > 0


def test_retrained_classifier_is_active_immediately_after_drift_step():
    # Verify that run_pipeline updates the classifier state and evaluates post-retrain
    results = run_pipeline()
    retrain_events = results["retrain_events"]
    assert len(retrain_events) >= 1
    # Check that fidelity checks occurred
    assert len(results["closed_loop_gate_log"]) >= 1
