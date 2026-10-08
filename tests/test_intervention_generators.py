"""Generators (SPEC v1.4): class purity, information set, determinism, clipping, controls."""
import ast
from pathlib import Path

import numpy as np
import pytest

import proteus.intervention.generators as gen_mod
from proteus.intervention.generators import (
    DonorSMOTE, FeatureShuffle, GaussianBlob, GeneratorError, MMDPrefilter, RandomOversampler,
    SMOTEGenerator, postprocess)


def rows(n=40, d=5, seed=0, shift=0.0):
    r = np.random.default_rng(seed)
    return (np.abs(r.normal(size=(n, d))) + shift).astype(np.float32)


# ------------------------------------------------------------------ information set / purity
def test_generators_see_only_the_rows_they_are_given_and_hold_a_copy():
    X = rows()
    for G in (RandomOversampler, SMOTEGenerator, GaussianBlob, FeatureShuffle):
        g = G().fit(X, 3, np.random.default_rng(0))
        assert np.array_equal(g.source_rows, X)
        X2 = X.copy()
        X[0, 0] += 100.0                                    # mutating the caller's array ...
        assert not np.array_equal(g.source_rows[0], X[0])   # ... must not change the generator
        X = X2


def test_ros_output_is_a_subset_of_the_input_rows_and_smote_stays_in_the_bounds():
    X = rows()
    ros = RandomOversampler().fit(X, 1, np.random.default_rng(0))
    out = ros.sample(200, np.random.default_rng(1))
    present = {tuple(r) for r in X}
    assert all(tuple(r) in present for r in out)
    sm = SMOTEGenerator().fit(X, 1, np.random.default_rng(0)).sample(500, np.random.default_rng(1))
    assert sm.shape == (500, 5) and sm.dtype == np.float32
    assert (sm >= X.min(axis=0) - 1e-6).all() and (sm <= X.max(axis=0) + 1e-6).all()
    assert len({tuple(r) for r in sm} - present) > 400      # genuinely new points, unlike ROS


def test_smote_neighbour_count_is_min_5_and_n_minus_1():
    assert SMOTEGenerator().fit(rows(40), 1, np.random.default_rng(0)).k == 5
    assert SMOTEGenerator().fit(rows(4), 1, np.random.default_rng(0)).k == 3
    assert SMOTEGenerator().fit(rows(2), 1, np.random.default_rng(0)).k == 1
    with pytest.raises(GeneratorError):
        SMOTEGenerator().fit(rows(1), 1, np.random.default_rng(0))


def test_smote_interpolates_between_neighbours_only():
    base = np.array([[0.0, 0.0], [1.0, 0.0], [100.0, 100.0]], dtype=np.float32)
    g = SMOTEGenerator().fit(base, 0, np.random.default_rng(0))     # k = 2: every row's neighbours
    out = g.sample(300, np.random.default_rng(2))
    assert ((out[:, 0] >= 0) & (out[:, 0] <= 100)).all()
    assert np.isfinite(out).all()


def test_determinism_and_stream_independence():
    X = rows()
    a = SMOTEGenerator().fit(X, 1, np.random.default_rng(5)).sample(50, np.random.default_rng(9))
    b = SMOTEGenerator().fit(X, 1, np.random.default_rng(5)).sample(50, np.random.default_rng(9))
    c = SMOTEGenerator().fit(X, 1, np.random.default_rng(5)).sample(50, np.random.default_rng(10))
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_sample_before_fit_and_zero_rows():
    with pytest.raises(GeneratorError):
        SMOTEGenerator().sample(3, np.random.default_rng(0))
    g = RandomOversampler().fit(rows(), 0, np.random.default_rng(0))
    assert g.sample(0, np.random.default_rng(0)).shape == (0, 5)


def test_postprocess_clips_and_keeps_nonnegative_features_nonnegative():
    bounds = np.array([[0.0, -2.0], [1.0, 2.0]], dtype=np.float32)
    out = postprocess(np.array([[-5.0, -9.0], [3.0, 9.0], [0.5, 0.0]]), bounds)
    assert out.min(axis=0).tolist() == [0.0, -2.0] and out.max(axis=0).tolist() == [1.0, 2.0]
    g = GaussianBlob().fit(rows(30), 0, np.random.default_rng(0)).sample(500, np.random.default_rng(1))
    assert (g >= 0).all()                                     # non-negative data stays non-negative


# ------------------------------------------------------------------ negative controls
def test_donor_smote_uses_only_donor_rows_and_ignores_the_target_class_rows():
    donor, target = rows(30, seed=1), rows(30, seed=2, shift=50.0)
    g = DonorSMOTE(donor).fit(target, 7, np.random.default_rng(0))
    assert np.array_equal(g.source_rows, donor)
    out = g.sample(100, np.random.default_rng(1))
    assert out.max() < 49.0                                   # nothing near the target class


def test_feature_shuffle_keeps_marginals_but_destroys_correlation():
    r = np.random.default_rng(0)
    z = r.normal(size=(400, 1))
    X = np.hstack([z, z + 0.01 * r.normal(size=(400, 1))]).astype(np.float32) + 10
    out = FeatureShuffle().fit(X, 0, np.random.default_rng(1)).sample(2000, np.random.default_rng(2))
    assert np.corrcoef(X.T)[0, 1] > 0.99 and abs(np.corrcoef(out.T)[0, 1]) < 0.2
    assert set(np.round(out[:, 0], 5)) <= set(np.round(X[:, 0], 5))


# ------------------------------------------------------------------ MMD pre-filter
class _Shifted:
    name = "SHIFT"

    def __init__(self, delta):
        self.delta = delta

    def fit(self, X, c, rng):
        self._X = np.asarray(X, dtype=np.float32)
        return self

    @property
    def source_rows(self):
        return self._X

    def sample(self, n, rng):
        return self._X[rng.integers(0, len(self._X), size=n)] + np.float32(self.delta)


def test_mmd_prefilter_admits_same_distribution_and_rejects_a_shifted_one():
    X = rows(120, d=6, seed=3)
    ok = MMDPrefilter(_Shifted(0.0), n_perm=60).fit(X, 1, np.random.default_rng(0))
    bad = MMDPrefilter(_Shifted(3.0), n_perm=60).fit(X, 1, np.random.default_rng(0))
    assert ok.admitted and ok.last_p > 0.05
    assert not bad.admitted and bad.last_p <= 0.05
    assert len(bad.sample(10, np.random.default_rng(0))) == 0
    assert len(ok.sample(10, np.random.default_rng(0))) == 10


# ------------------------------------------------------------------ static isolation
def test_module_has_no_path_to_partitions_or_evaluation_data():
    src = Path(gen_mod.__file__).read_text()
    tree = ast.parse(src)
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    forbidden = {"proteus.intervention.protocol", "proteus.intervention.cache",
                 "proteus.intervention.learner", "proteus.intervention.p0"}
    assert not (imported & forbidden)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"sel_X", "gate_X", "s_sel_X", "s_gate_X", "e_idx", "s_report_idx", "ControllerView"} & names
