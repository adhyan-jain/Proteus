"""Learner tests: candidate construction, measurability, affected region, eligible set."""
from dataclasses import replace

import numpy as np
import pytest

import proteus.intervention.learner as learner_mod
from proteus.intervention.learner import (
    CandidateBuilder, RFModel, TrainingAddition, compute_affected_region, compute_residual_sets,
    measurable_classes, require_view)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import ControllerView
from tests.test_intervention_promotion import FakeModel, make_params, make_view

NAMES = ("benign", "a", "b")
K = 3
D = 4


def _blob(rng, cls, n):
    return (rng.normal(size=(n, D)) + 6.0 * cls).astype(np.float32)


def _rows(rng, counts):
    X = np.vstack([_blob(rng, c, n) for c, n in counts.items()])
    y = np.concatenate([np.full(n, c, dtype=np.int64) for c, n in counts.items()])
    return X, y


def make_learnable_view(seed=0, real_counts=None, sel_counts=None, gate_counts=None):
    rng = np.random.default_rng(seed)
    parts = {
        "ref": _rows(rng, {0: 300, 1: 300}),                       # b never seen pre-drift
        "real": _rows(rng, real_counts or {0: 60, 1: 60, 2: 60}),
        "sel": _rows(rng, sel_counts or {0: 80, 1: 40, 2: 40}),
        "gate": _rows(rng, gate_counts or {0: 80, 1: 40, 2: 40}),
        "s_sel": _rows(rng, {0: 100, 1: 100}),
        "s_gate": _rows(rng, {0: 100, 1: 100}),
    }
    return ControllerView(
        ref_X=parts["ref"][0], ref_y=parts["ref"][1], real_X=parts["real"][0],
        real_y=parts["real"][1], sel_X=parts["sel"][0], sel_y=parts["sel"][1],
        gate_X=parts["gate"][0], gate_y=parts["gate"][1], s_sel_X=parts["s_sel"][0],
        s_sel_y=parts["s_sel"][1], s_gate_X=parts["s_gate"][0], s_gate_y=parts["s_gate"][1],
        class_names=NAMES)


def params(**kw):
    return InterventionParams(benign_label="benign", rf_n_estimators=25, **kw)  # 25 trees: speed


@pytest.fixture(scope="module")
def view():
    return make_learnable_view()


@pytest.fixture(scope="module")
def incumbent(view):
    return CandidateBuilder(params(), seed=0).build_base(view)


def test_builder_trains_on_ref_plus_real_only(view):
    m = CandidateBuilder(params(), seed=0).build(view)
    assert isinstance(m, RFModel)
    assert m.n_train_rows == len(view.ref_X) + len(view.real_X)
    assert set(m.classes_.tolist()) == {0, 1, 2}
    assert (m.predict(_blob(np.random.default_rng(1), 2, 50)) == 2).mean() > 0.95


def test_builder_is_deterministic_and_does_not_touch_the_incumbent(view, incumbent):
    before = incumbent.predict(view.gate_X).copy()
    a = CandidateBuilder(params(), seed=3).build(view)
    b = CandidateBuilder(params(), seed=3).build(view)
    probe = np.random.default_rng(9).normal(size=(200, D)).astype(np.float32) * 5
    assert np.array_equal(a.predict(probe), b.predict(probe))
    assert np.array_equal(incumbent.predict(view.gate_X), before)
    assert a.clf is not incumbent.clf


def test_training_addition_is_the_only_plug_in_point(view):
    extra = TrainingAddition(X=_blob(np.random.default_rng(2), 2, 30),
                             y=np.full(30, 2, dtype=np.int64), source="test")
    m = CandidateBuilder(params(), seed=0).build(view, extra=extra)
    assert m.n_train_rows == len(view.ref_X) + len(view.real_X) + 30
    with pytest.raises(ValueError):
        CandidateBuilder(params(), seed=0).build(
            view, extra=TrainingAddition(X=np.zeros((3, D + 1), np.float32),
                                         y=np.zeros(3, np.int64), source="bad"))
    with pytest.raises(ValueError):
        TrainingAddition(X=np.zeros((3, D), np.float32), y=np.zeros(2, np.int64), source="bad")


def test_learner_entry_points_reject_non_views(incumbent):
    for call in (lambda: CandidateBuilder(params(), 0).build({"ref_X": 1}),
                 lambda: compute_affected_region(None, incumbent, params(),
                                                 np.random.default_rng(0)),
                 lambda: compute_residual_sets("view", incumbent, (2,), params(),
                                               np.random.default_rng(0)),
                 lambda: CandidateBuilder(params(), 0).build_base([1, 2, 3]),
                 lambda: require_view(object())):
        with pytest.raises(TypeError):
            call()


def test_measurable_needs_support_in_both_sel_and_gate():
    v = make_learnable_view(sel_counts={0: 80, 1: 40, 2: 40}, gate_counts={0: 80, 1: 40, 2: 4})
    assert measurable_classes(v, params()) == (0, 1)            # b has only 4 gate rows
    v = make_learnable_view(sel_counts={0: 80, 1: 40, 2: 5}, gate_counts={0: 80, 1: 40, 2: 5})
    assert measurable_classes(v, params()) == (0, 1, 2)         # exactly s_min counts
    assert measurable_classes(v, params(s_min=6)) == (0, 1)


def test_affected_region_is_the_measurable_deficient_class(view, incumbent):
    info = compute_affected_region(view, incumbent, params(), np.random.default_rng(0))
    assert info.measurable == (0, 1, 2)
    # The incumbent never saw b and labels it as the nearest class a, so b has F1 = 0 and a
    # loses precision (one-vs-rest F1) -- both are deficient; benign is untouched.
    assert info.region == (1, 2)
    assert info.deficiency_lcb[2] > 0.9 and info.deficiency_lcb[0] < 0.05


def test_unmeasurable_deficient_class_is_not_in_the_region(incumbent):
    v = make_learnable_view(gate_counts={0: 80, 1: 40, 2: 3})
    info = compute_affected_region(v, incumbent, params(), np.random.default_rng(0))
    assert 2 not in info.measurable and 2 not in info.region   # b has F1 0 but cannot be measured
    assert info.region == (1,)      # a is still deficient: b rows are predicted as a (precision)
    v = make_learnable_view(gate_counts={0: 80, 1: 3, 2: 3})
    info = compute_affected_region(v, incumbent, params(), np.random.default_rng(0))
    assert info.measurable == (0,) and info.region == ()


def test_region_without_any_measurable_class_never_calls_the_model():
    class Boom:
        def predict(self, X):
            raise AssertionError("model must not be called")

    v = make_learnable_view(sel_counts={0: 2, 1: 2, 2: 2}, gate_counts={0: 2, 1: 2, 2: 2})
    info = compute_affected_region(v, Boom(), params(), np.random.default_rng(0))
    assert info.region == () and info.measurable == ()


def test_eligible_set_reflects_residual_deficiency_and_real_support(view, incumbent):
    region = (2,)
    fixed = CandidateBuilder(params(), seed=0).build(view)
    rng = lambda: np.random.default_rng(0)  # noqa: E731
    assert compute_residual_sets(view, fixed, region, params(), rng()).eligible == ()
    # a candidate that still misses class b is eligible when enough real b rows exist ...
    assert compute_residual_sets(view, incumbent, region, params(), rng()).eligible == (2,)
    # ... and not when fewer than n_min real fit rows of b exist
    thin = replace(view, real_X=view.real_X[view.real_y != 2],
                   real_y=view.real_y[view.real_y != 2])
    assert compute_residual_sets(thin, incumbent, region, params(), rng()).eligible == ()
    assert compute_residual_sets(view, incumbent, (), params(), rng()) == \
        compute_residual_sets(view, incumbent, (), params(), rng())
    assert compute_residual_sets(view, incumbent, (), params(), rng()).eligible == ()


def test_eligibility_uses_recall_and_logs_f1_only_as_a_diagnostic():
    """Collateral-benign case: the model has never seen b and calls every b row benign. BENIGN's
    recall is perfect but its precision (hence F1) drops, so an F1-based I would list BENIGN as
    having 'residual deficiency' that no amount of extra BENIGN data can repair."""
    view, truth, ranges = make_view()
    table = truth.copy()
    table[truth == 2] = 0                           # b -> benign
    model = FakeModel(table)
    rng = lambda: np.random.default_rng(0)  # noqa: E731
    p = make_params()
    res = compute_residual_sets(view, model, (0, 2), p, rng())
    assert res.eligible == (2,)                     # b: recall 0 and 40 real rows to learn from
    assert res.f1_diagnostic == (0, 2)              # F1 also flags the polluted BENIGN
    # the false-GO situation: b has too few real rows to be eligible, only BENIGN is flagged by F1
    keep = np.concatenate([np.flatnonzero(view.real_y != 2),
                           np.flatnonzero(view.real_y == 2)[:3]])       # only 3 real b rows
    thin = replace(view, real_X=view.real_X[keep], real_y=view.real_y[keep])
    res = compute_residual_sets(thin, model, (0, 2), p, rng())
    assert res.eligible == ()                       # honest: nothing the controller could fix
    assert res.f1_diagnostic == (0,)                # an F1-based I would have said 'room exists'


# ----------------------------------------------------------------------------- D1: base model
def _capture_fits(monkeypatch):
    calls = []
    original = learner_mod._fit_rf

    def spy(X, y, params, seed):
        calls.append((np.array(X), np.array(y), seed))
        return original(X, y, params, seed)

    monkeypatch.setattr(learner_mod, "_fit_rf", spy)
    return calls


def test_base_model_is_fit_on_exactly_d_ref(view, monkeypatch):
    calls = _capture_fits(monkeypatch)
    base = CandidateBuilder(params(), seed=4).build_base(view)
    (X, y, seed), = calls
    assert np.array_equal(X, view.ref_X) and np.array_equal(y, view.ref_y)
    assert seed == 4 and base.n_train_rows == len(view.ref_X)
    assert set(base.classes_.tolist()) == {0, 1}          # never saw the drift class


def test_candidate_training_set_nests_the_base_training_set(view, monkeypatch):
    calls = _capture_fits(monkeypatch)
    builder = CandidateBuilder(params(), seed=0)
    builder.build_base(view)
    builder.build(view)
    (Xb, yb, sb), (Xc, yc, sc) = calls
    n = len(Xb)
    assert sb == sc                                          # same learner seed
    assert np.array_equal(Xc[:n], Xb) and np.array_equal(yc[:n], yb)   # base is a prefix
    assert np.array_equal(Xc[n:], view.real_X) and len(Xc) == n + len(view.real_X)


def test_base_construction_is_deterministic(view):
    a = CandidateBuilder(params(), seed=2).build_base(view)
    b = CandidateBuilder(params(), seed=2).build_base(view)
    probe = np.random.default_rng(6).normal(size=(300, D)).astype(np.float32) * 6
    assert np.array_equal(a.predict(probe), b.predict(probe))
    assert np.allclose(a.predict_proba(probe), b.predict_proba(probe))


def test_base_does_not_depend_on_other_view_fields(view):
    other = replace(view, real_y=np.zeros_like(view.real_y), gate_y=np.zeros_like(view.gate_y),
                    sel_y=np.zeros_like(view.sel_y))
    probe = np.random.default_rng(7).normal(size=(300, D)).astype(np.float32) * 6
    a = CandidateBuilder(params(), seed=2).build_base(view)
    b = CandidateBuilder(params(), seed=2).build_base(other)
    assert np.array_equal(a.predict(probe), b.predict(probe))
