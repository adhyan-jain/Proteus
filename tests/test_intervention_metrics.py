"""Tests for proteus.intervention.metrics: definitions, paired bootstrap, t-interval."""
import numpy as np
import pytest
from sklearn.metrics import f1_score

from proteus.intervention.metrics import (
    benign_fpr_conf, bootstrap_confusions, confusion, f1_from_conf, lcb, region_utility_conf,
    stable_macro_f1_conf, t_ci, ucb)

K = 5


def _random_case(n=2000, seed=0, acc=0.8):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, K, size=n)
    pred = np.where(rng.random(n) < acc, y, rng.integers(0, K, size=n))
    return y, pred


def test_f1_from_conf_matches_sklearn():
    y, pred = _random_case()
    ours = f1_from_conf(confusion(y, pred, K))
    ref = f1_score(y, pred, labels=list(range(K)), average=None, zero_division=0)
    assert np.allclose(ours, ref)


def test_f1_is_zero_for_absent_class_and_vectorises_over_replicates():
    conf = np.zeros((K, K), dtype=int)
    conf[0, 0] = 10
    f1 = f1_from_conf(conf)
    assert f1[0] == 1.0 and (f1[1:] == 0).all()
    stacked = np.stack([conf, conf])
    assert f1_from_conf(stacked).shape == (2, K)


def test_region_and_stable_utilities():
    y, pred = _random_case()
    conf = confusion(y, pred, K)
    f1 = f1_from_conf(conf)
    assert region_utility_conf(conf, {1, 3}) == pytest.approx((f1[1] + f1[3]) / 2)
    assert stable_macro_f1_conf(conf, [0, 2, 4]) == pytest.approx(f1[[0, 2, 4]].mean())
    with pytest.raises(ValueError):
        region_utility_conf(conf, set())
    with pytest.raises(ValueError):
        stable_macro_f1_conf(conf, [])


def test_benign_fpr_and_nan_when_no_benign_rows():
    y = np.array([0, 0, 0, 0, 1, 1])
    pred = np.array([0, 0, 1, 2, 1, 1])
    assert benign_fpr_conf(confusion(y, pred, K), 0) == pytest.approx(0.5)
    assert np.isnan(benign_fpr_conf(confusion(np.array([1, 1]), np.array([1, 0]), K), 0))


def test_bootstrap_conserves_class_sizes_and_is_reproducible():
    y, pred = _random_case()
    a = bootstrap_confusions(y, [pred], K, 200, np.random.default_rng(3))[0]
    b = bootstrap_confusions(y, [pred], K, 200, np.random.default_rng(3))[0]
    assert np.array_equal(a, b)
    point = confusion(y, pred, K)
    assert (a.sum(axis=2) == point.sum(axis=1)).all()   # every replicate keeps the class sizes


def test_bootstrap_centres_on_point_estimate_with_binomial_spread():
    # one class, 150/200 correct: recall ~ 0.75, std ~ sqrt(.75*.25/200) = 0.0306
    y = np.zeros(200, dtype=int)
    pred = np.concatenate([np.zeros(150, int), np.ones(50, int)])
    conf = bootstrap_confusions(y, [pred], 2, 4000, np.random.default_rng(0))[0]
    recall = conf[:, 0, 0] / conf[:, 0, :].sum(axis=1)
    assert recall.mean() == pytest.approx(0.75, abs=0.005)
    assert recall.std() == pytest.approx(np.sqrt(0.75 * 0.25 / 200), rel=0.1)


def test_paired_bootstrap_of_identical_models_has_zero_difference():
    y, pred = _random_case()
    ca, cb = bootstrap_confusions(y, [pred, pred.copy()], K, 300, np.random.default_rng(1))
    diff = region_utility_conf(ca, {0, 1}) - region_utility_conf(cb, {0, 1})
    assert np.all(diff == 0)


def test_paired_bootstrap_detects_a_real_improvement_but_not_a_tie():
    rng = np.random.default_rng(5)
    y = rng.integers(0, K, size=3000)
    good = np.where(rng.random(3000) < 0.9, y, rng.integers(0, K, size=3000))
    bad = np.where(rng.random(3000) < 0.6, y, rng.integers(0, K, size=3000))
    ca, cb = bootstrap_confusions(y, [good, bad], K, 1000, np.random.default_rng(2))
    d = region_utility_conf(ca, {0, 1, 2}) - region_utility_conf(cb, {0, 1, 2})
    assert lcb(d, 0.05) > 0.1
    other = np.where(rng.random(3000) < 0.9, y, rng.integers(0, K, size=3000))
    ca, cb = bootstrap_confusions(y, [good, other], K, 1000, np.random.default_rng(2))
    d = region_utility_conf(ca, {0, 1, 2}) - region_utility_conf(cb, {0, 1, 2})
    assert lcb(d, 0.05) < 0 < ucb(d, 0.05)


def test_bootstrap_rejects_length_mismatch():
    with pytest.raises(ValueError):
        bootstrap_confusions(np.zeros(5, int), [np.zeros(4, int)], K, 10, np.random.default_rng(0))


def test_lcb_ucb_ordering_and_nan_handling():
    x = np.arange(101, dtype=float)
    assert lcb(x, 0.05) == pytest.approx(5.0)
    assert ucb(x, 0.05) == pytest.approx(95.0)
    assert lcb(x, 0.05) < ucb(x, 0.05)
    assert np.isnan(lcb(np.array([np.nan, np.nan]), 0.05))
    assert lcb(np.array([np.nan, 1.0, 2.0]), 0.5) == pytest.approx(1.5)


def test_t_ci_uses_the_t_distribution_not_1_96():
    ci = t_ci([1, 2, 3, 4, 5])
    se = np.std([1, 2, 3, 4, 5], ddof=1) / np.sqrt(5)
    assert ci["mean"] == 3.0
    assert ci["half_width"] == pytest.approx(2.7764451 * se, rel=1e-5)
    assert ci["half_width"] > 1.96 * se
    assert (ci["lo"], ci["hi"]) == pytest.approx((3 - ci["half_width"], 3 + ci["half_width"]))


def test_t_ci_with_one_value_has_no_interval():
    ci = t_ci([0.4])
    assert ci["mean"] == 0.4 and np.isnan(ci["lo"]) and np.isnan(ci["hi"]) and ci["n"] == 1
