"""Real behavioral tests for the MMD fidelity gate (proteus/fidelity.py), shared by the demo
and full-scale backends. No dataset needed -- these test the mechanism, not a research claim."""
import numpy as np

from proteus.fidelity import compute_mmd, admit, FidelityGateLog


def test_mmd_zero_for_identical_distribution():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 5))
    assert compute_mmd(X, X) == 0.0


def test_mmd_near_zero_for_same_distribution_different_samples():
    rng = np.random.default_rng(1)
    X = rng.normal(loc=0.0, scale=1.0, size=(300, 5))
    Y = rng.normal(loc=0.0, scale=1.0, size=(300, 5))
    assert compute_mmd(X, Y) < 0.05


def test_mmd_large_for_clearly_different_distributions():
    rng = np.random.default_rng(2)
    X = rng.normal(loc=0.0, scale=1.0, size=(300, 5))
    Y = rng.normal(loc=20.0, scale=1.0, size=(300, 5))
    same_dist = compute_mmd(X, rng.normal(loc=0.0, scale=1.0, size=(300, 5)))
    diff_dist = compute_mmd(X, Y)
    assert diff_dist > same_dist


def test_mmd_never_negative():
    rng = np.random.default_rng(3)
    for _ in range(20):
        X = rng.normal(size=(50, 3))
        Y = rng.normal(loc=rng.uniform(-5, 5), size=(50, 3))
        assert compute_mmd(X, Y) >= 0.0


def test_admit_direction():
    # Lower MMD (more similar) must admit; higher MMD (less similar) must reject.
    assert admit(mmd_score=0.01, threshold=0.25) is True
    assert admit(mmd_score=0.5, threshold=0.25) is False


def test_gate_log_records_every_check_and_matches_admit_decision():
    rng = np.random.default_rng(4)
    gate = FidelityGateLog(threshold=0.25)
    real = rng.normal(size=(200, 4))
    similar_synth = real + rng.normal(scale=0.01, size=(200, 4))
    different_synth = rng.normal(loc=50.0, size=(200, 4))

    admitted1, score1 = gate.check(step=0, synthetic_batch=similar_synth, real_batch=real,
                                    n_samples=200)
    admitted2, score2 = gate.check(step=1, synthetic_batch=different_synth, real_batch=real,
                                    n_samples=200)

    assert admitted1 is True
    assert admitted2 is False
    assert len(gate.entries) == 2
    assert gate.entries[0]["admitted"] == admitted1
    assert gate.entries[1]["admitted"] == admitted2
    assert gate.entries[0]["mmd_score"] == score1
