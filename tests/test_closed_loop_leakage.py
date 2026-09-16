"""Regression test for a real train/test-leakage bug found and fixed during the 2026-09-17
autonomous audit: ClosedLoopOrchestrator.step() used to retrain the classifier on
(X_train + window) and then score macro_f1_after on that same window -- in-sample training
accuracy reported as a post-adaptation metric. Fixed via ClosedLoopOrchestrator.split_eval_fit,
which this test verifies directly (no GPU/GAN checkpoint needed -- it's a pure numpy split)."""
import numpy as np

from proteus.closed_loop_full import ClosedLoopOrchestrator


def test_eval_and_fit_partitions_are_disjoint_and_cover_the_window():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(1000, 4))
    y = rng.integers(0, 5, size=1000)
    split_rng = np.random.default_rng(42)

    X_eval, y_eval, X_fit, y_fit = ClosedLoopOrchestrator.split_eval_fit(
        X, y, fraction=0.3, rng=split_rng)

    assert len(X_eval) + len(X_fit) == len(X)
    assert len(y_eval) + len(y_fit) == len(y)
    # No row in the eval split may also appear in the fit split (checked by identity via a
    # round-trip through a set of tuples, since these are small float feature vectors from a
    # controlled synthetic source with no duplicate rows).
    eval_rows = {tuple(row) for row in X_eval}
    fit_rows = {tuple(row) for row in X_fit}
    assert eval_rows.isdisjoint(fit_rows)


def test_eval_fraction_is_respected_approximately():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(2000, 3))
    y = rng.integers(0, 3, size=2000)
    X_eval, y_eval, X_fit, y_fit = ClosedLoopOrchestrator.split_eval_fit(
        X, y, fraction=0.3, rng=np.random.default_rng(7))
    assert len(X_eval) == 600
    assert len(X_fit) == 1400


def test_split_is_reproducible_given_same_rng_state():
    rng_state_a = np.random.default_rng(123)
    rng_state_b = np.random.default_rng(123)
    X = np.arange(100).reshape(-1, 1).astype(float)
    y = np.arange(100)

    a = ClosedLoopOrchestrator.split_eval_fit(X, y, 0.3, rng_state_a)
    b = ClosedLoopOrchestrator.split_eval_fit(X, y, 0.3, rng_state_b)
    for arr_a, arr_b in zip(a, b):
        assert np.array_equal(arr_a, arr_b)


def test_minimum_one_eval_row_even_for_tiny_windows():
    X = np.arange(2).reshape(-1, 1).astype(float)
    y = np.array([0, 1])
    X_eval, y_eval, X_fit, y_fit = ClosedLoopOrchestrator.split_eval_fit(
        X, y, fraction=0.01, rng=np.random.default_rng(0))
    assert len(X_eval) >= 1
