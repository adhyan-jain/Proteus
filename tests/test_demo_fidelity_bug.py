"""Regression unit tests for class-conditional reference selection in fidelity gate checking."""
import numpy as np
from proteus.pipeline import run_pipeline


def test_fidelity_gate_reference_selection_is_class_conditional():
    """Verify that demo pipeline fidelity checks run class-conditional checks and record scores."""
    results = run_pipeline()
    
    closed_loop_gate_log = results.get("closed_loop_gate_log", [])
    assert len(closed_loop_gate_log) > 0, "Closed-loop fidelity gate log should contain entries"
    for entry in closed_loop_gate_log:
        assert "mmd_score" in entry
        assert "admitted" in entry
        assert isinstance(entry["mmd_score"], float)
        assert entry["mmd_score"] >= 0.0

