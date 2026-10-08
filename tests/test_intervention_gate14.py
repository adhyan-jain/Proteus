"""promote_star (SPEC v1.4 J.1) and canary (J.2) on hand-built views with scripted models."""
import numpy as np
import pytest

from proteus.intervention.gate14 import canary, promote_star
from tests.test_intervention_promotion import (
    FakeModel, make_params, make_view, _rows)

REGION = (2,)


@pytest.fixture()
def world():
    view, truth, ranges = make_view()
    inc_table = truth.copy()
    inc_table[truth == 2] = 0                       # incumbent / anchor never recognise class 2
    return view, truth, ranges, FakeModel(inc_table), inc_table


def table_with(truth, inc_table, frac_gate, ranges, extra=None):
    """Recognises `frac_gate` of the class-2 rows of D_gate (and all of the other segments)."""
    t = truth.copy()
    g2 = _rows(ranges, truth, "gate", 2)
    t[g2[int(round(frac_gate * len(g2))):]] = 0
    for seg in ("sel", "real", "ref", "s_sel", "s_gate"):
        pass
    return t


def go(view, inc, theta_R, star, params=None, anchor=None):
    p = params or make_params()
    return promote_star(view, inc, theta_R, star, REGION, p, np.random.default_rng(1),
                        np.random.default_rng(2), inc if anchor is None else anchor,
                        np.random.default_rng(3))


def test_better_star_is_promoted_on_the_star_branch(world):
    view, truth, ranges, inc, inc_table = world
    theta_R = FakeModel(table_with(truth, inc_table, 0.6, ranges))
    star = FakeModel(truth.copy())
    d = go(view, inc, theta_R, star)
    assert d.promoted and d.branch == "star" and d.reason == "promoted" and d.model is star
    assert d.noninferiority["point"] > 0 and d.noninferiority["lcb"] >= -0.01
    assert d.real_decision is None


def test_star_that_adds_nothing_over_real_falls_back_to_real_only(world):
    view, truth, ranges, inc, inc_table = world
    t = table_with(truth, inc_table, 0.8, ranges)
    theta_R, star = FakeModel(t), FakeModel(t.copy())
    d = go(view, inc, theta_R, star)
    assert d.promoted and d.branch == "real_only" and d.model is theta_R
    assert d.star_reason == "star_no_gain_over_real" and d.reason == "promoted"


def test_star_worse_than_real_is_not_promoted_and_real_is(world):
    view, truth, ranges, inc, inc_table = world
    theta_R = FakeModel(table_with(truth, inc_table, 1.0, ranges))
    t = table_with(truth, inc_table, 0.7, ranges)               # recognises fewer class-2 rows
    d = go(view, inc, theta_R, FakeModel(t))
    assert d.branch == "real_only" and d.star_reason == "star_no_gain_over_real"


def test_star_inferior_is_distinguished_from_no_gain(world):
    view, truth, ranges, inc, inc_table = world
    g2 = _rows(ranges, truth, "gate", 2)
    t_r = truth.copy()
    t_r[g2[:6]] = 0                                             # theta_R misses 6 class-2 rows
    t_s = truth.copy()
    t_s[g2[6:11]] = 0                                           # theta* fixes those 6 but misses 5 others
    d = go(view, inc, FakeModel(t_r), FakeModel(t_s))
    assert d.noninferiority["point"] > 0 and d.noninferiority["lcb"] < -0.01
    assert d.star_reason == "star_inferior_to_real"
    assert d.branch == "real_only" and d.model.table is not None


def test_star_that_breaks_the_envelope_is_rejected_and_real_is_used(world):
    view, truth, ranges, inc, inc_table = world
    theta_R = FakeModel(table_with(truth, inc_table, 0.6, ranges))
    t = truth.copy()
    s_gate_lo, s_gate_hi = ranges["s_gate"]
    ben = s_gate_lo + np.flatnonzero(truth[s_gate_lo:s_gate_hi] == 0)[:40]
    t[ben] = 1                                                  # 40 benign stable rows flagged
    d = go(view, inc, theta_R, FakeModel(t))
    assert d.star_reason.startswith("envelope_") and d.branch == "real_only"
    assert d.star_report is not None and not d.star_report.envelope_ok


def test_no_star_equals_the_unchanged_real_only_rule_and_empty_region_keeps_the_incumbent(world):
    view, truth, ranges, inc, inc_table = world
    theta_R = FakeModel(table_with(truth, inc_table, 0.9, ranges))
    d = go(view, inc, theta_R, None)
    assert d.promoted and d.branch == "real_only" and d.star_reason == "no_star"
    d2 = go(view, inc, theta_R, theta_R)                         # k == 0: th* is th_R itself
    assert d2.star_reason == "no_star" and d2.model is theta_R
    e = promote_star_empty(view, inc)
    assert not e.promoted and e.reason == "no_affected_region" and e.model is inc


def promote_star_empty(view, inc):
    return promote_star(view, inc, None, None, (), make_params(), np.random.default_rng(0),
                        np.random.default_rng(0), inc)


def test_star_must_beat_the_incumbent_not_only_real(world):
    view, truth, ranges, inc, inc_table = world
    star = FakeModel(inc_table.copy())                           # no better than the incumbent
    theta_R = FakeModel(table_with(truth, inc_table, 0.0, ranges))
    d = go(view, inc, theta_R, star)
    assert not d.promoted and d.branch == "incumbent" and d.model is inc
    assert d.star_reason.startswith("utility_")


# ------------------------------------------------------------------------------ canary
def _canary(world, new_table, prev_table=None, anchor_table=None):
    view, truth, ranges, inc, inc_table = world
    lo, hi = ranges["gate"]
    X, y = view.gate_X, view.gate_y
    p = make_params()
    return canary(FakeModel(new_table), FakeModel(inc_table if prev_table is None else prev_table),
                  FakeModel(inc_table if anchor_table is None else anchor_table), X, y, REGION, p,
                  np.random.default_rng(0), benign=0, n_classes=3)


def test_canary_keeps_a_model_that_is_better_and_rolls_back_one_that_is_significantly_worse(world):
    view, truth, ranges, inc, inc_table = world
    good = truth.copy()
    d = _canary(world, good)
    assert not d.rollback and d.reason == "keep"
    prev_good = truth.copy()
    bad = truth.copy()
    bad[truth == 2] = 0                                          # new model lost the drift class
    d2 = _canary(world, bad, prev_table=prev_good)
    assert d2.rollback and d2.reason == "utility_worse" and d2.stats["utility_diff_ucb"] < 0


def test_canary_rolls_back_on_an_established_benign_fpr_violation_only(world):
    view, truth, ranges, inc, inc_table = world
    new = truth.copy()
    ben = np.flatnonzero((truth == 0))
    gate_lo, gate_hi = ranges["gate"]
    gate_ben = gate_lo + np.flatnonzero(truth[gate_lo:gate_hi] == 0)
    new[gate_ben[:20]] = 1                                       # 20 of 100 gate benign rows flagged
    d = _canary(world, new, prev_table=new)                      # utility equal to prev ...
    assert d.rollback and d.reason == "fpr_envelope_violated"
    few = truth.copy()
    few[gate_ben[:1]] = 1                                        # one flagged row: not established
    d2 = _canary(world, few, prev_table=few)
    assert not d2.rollback


def test_canary_without_evidence_never_rolls_back(world):
    view, truth, ranges, inc, inc_table = world
    p = make_params()
    d = canary(FakeModel(truth), FakeModel(inc_table), FakeModel(inc_table), view.gate_X[:0],
               view.gate_y[:0], REGION, p, np.random.default_rng(0), benign=0, n_classes=3)
    assert not d.rollback and d.reason == "no_evidence"
    d2 = canary(FakeModel(truth), FakeModel(inc_table), FakeModel(inc_table), view.gate_X,
                view.gate_y, (), p, np.random.default_rng(0), benign=0, n_classes=3)
    assert not d2.rollback and d2.reason == "no_evidence"
