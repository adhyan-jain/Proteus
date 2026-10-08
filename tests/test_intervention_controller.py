"""Controller (SPEC v1.4 section 3.1): stop reasons, step statistics, safety filter, isolation.

Search logic is tested with scripted models (a FakeModel answers from a per-row-id table) and a
scripted operator, so each test controls exactly which rows each candidate gets right."""
import json
import types
from dataclasses import replace

import numpy as np
import pytest

import proteus.intervention.controller as ctl
from proteus.intervention.conditions import DecisionContext
from proteus.intervention.controller import (
    ControllerOptions, DataOperator, InterventionController, ThreshModel, ThresholdOperator,
    WEIGHT_LADDER, sub_rng)
from proteus.intervention.generators import SMOTEGenerator
from proteus.intervention.learner import CandidateBuilder, ResidualSets
from tests.test_intervention_learner import make_learnable_view
from tests.test_intervention_promotion import FakeModel, make_params, make_view


class ScriptedOp:
    name = "SCRIPT"

    def __init__(self, build_fn, max_rung=3, feasible=True):
        self.build_fn, self.max_rung, self._feasible = build_fn, max_rung, feasible
        self.fit_errors, self.generators = {}, {}

    def prepare(self, view, builder, theta_R, classes, params, ctx):
        pass

    def next_dose(self, c, doses):
        r = doses.get(c, 0)
        cap = self.max_rung[c] if isinstance(self.max_rung, dict) else self.max_rung
        return r + 1 if r + 1 <= cap else None

    def feasible(self, doses):
        return self._feasible

    def n_syn(self, doses):
        return 10 * sum(doses.values())

    def build(self, doses):
        return FakeModel(self.build_fn(dict(doses)))

    def describe(self, doses):
        return {"n_syn": self.n_syn(doses), "per_class": {str(c): r for c, r in doses.items()}}


@pytest.fixture()
def world(monkeypatch):
    view, truth, ranges = make_view()
    sel_lo, sel_hi = ranges["sel"]
    cls2_sel = sel_lo + np.flatnonzero(truth[sel_lo:sel_hi] == 2)
    inc_table = truth.copy()
    inc_table[truth == 2] = 0
    base = types.SimpleNamespace(table=inc_table)

    def with_recognised(table, rows):
        t = table.copy()
        t[rows] = 2
        return t

    class W:
        pass

    w = W()
    w.view, w.truth, w.ranges, w.cls2_sel = view, truth, ranges, cls2_sel
    w.inc = FakeModel(inc_table)
    w.inc_table = inc_table
    w.recognise = with_recognised
    w.params = make_params()
    w.ctx = DecisionContext(t=6, seed=1, params=w.params, anchor=w.inc)
    # theta_R: recognises none of class 2 (so every gain is attributable to the operator)
    monkeypatch.setattr(ctl, "CandidateBuilder",
                        lambda params, seed: types.SimpleNamespace(
                            build=lambda view, extra=None: FakeModel(inc_table)))
    monkeypatch.setattr(ctl, "compute_residual_sets",
                        lambda *a, **k: ResidualSets((2,), ()))
    return w


def run(w, op, options=ControllerOptions(), params=None):
    ctx = w.ctx if params is None else replace(w.ctx, params=params)
    return InterventionController(op, options).run(w.view, w.inc, ctx, anchor=w.inc)


def improving(w, fractions):
    """rung r recognises the first fractions[r] share of class-2 rows of D_sel (and the rest)."""
    def build(doses):
        r = max(doses.values()) if doses else 0
        frac = fractions[min(r, len(fractions) - 1)]
        rows = np.flatnonzero(w.truth == 2)
        chosen = rows[(np.arange(len(rows)) % 10) < int(round(frac * 10))]   # spread over segments
        return w.recognise(w.inc_table, chosen)
    return build


# ------------------------------------------------------------------ trivial exits
def test_empty_region_is_a_noop(world):
    w = world
    perfect = FakeModel(w.truth)
    out = InterventionController(ScriptedOp(improving(w, [1.0]))).run(
        w.view, perfect, replace(w.ctx, anchor=perfect), anchor=perfect)
    assert out.stop_reason == "no_affected_region" and out.theta_R is None and out.k == 0


def test_real_only_sufficient_returns_theta_R_itself(world, monkeypatch):
    monkeypatch.setattr(ctl, "compute_residual_sets", lambda *a, **k: ResidualSets((), ()))
    out = run(world, ScriptedOp(improving(world, [1.0])))
    assert out.stop_reason == "real_only_sufficient" and out.k == 0
    assert out.theta_star is out.theta_R and out.steps == []


# ------------------------------------------------------------------ stop reasons
def test_greedy_accepts_improving_steps_then_stops_on_no_gain(world):
    out = run(world, ScriptedOp(improving(world, [0.0, 0.4, 0.8, 0.8, 0.8]), max_rung=4))
    assert out.k == 2 and out.stop_reason == "no_gain" and out.doses == {2: 2}
    assert [s["accepted"] for s in out.steps] == [2, 2, None]
    assert out.steps[-1]["candidates"][0]["gain_lcb"] <= world.params.eta


def test_k_max_stops_the_search(world):
    p = make_params(k_max=2)
    out = run(world, ScriptedOp(improving(world, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]), max_rung=5),
              params=p)
    assert out.k == 2 and out.stop_reason == "k_max"
    out1 = run(world, ScriptedOp(improving(world, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]), max_rung=5),
               ControllerOptions(k_cap=1))
    assert out1.k == 1 and out1.stop_reason == "k_max"


def test_no_admissible_action_when_the_ladder_is_exhausted_or_infeasible(world):
    assert run(world, ScriptedOp(improving(world, [1.0]), max_rung=0)).stop_reason == "no_admissible"
    out = run(world, ScriptedOp(improving(world, [1.0]), max_rung=3, feasible=False))
    assert out.stop_reason == "no_admissible" and out.k == 0 and out.theta_star is out.theta_R


def _flip_benign(w, table, n=30):
    sel_lo, sel_hi = w.ranges["sel"]
    ben = sel_lo + np.flatnonzero(w.truth[sel_lo:sel_hi] == 0)[:n]
    t = table.copy()
    t[ben] = 1
    return t


def test_unsafe_improvement_is_filtered_unless_the_filter_is_ablated(world):
    w = world
    build = lambda d: _flip_benign(w, improving(w, [0.0, 1.0])(d))
    out = run(w, ScriptedOp(build, max_rung=1))
    assert out.stop_reason == "no_safe_candidate" and out.k == 0
    c = out.steps[0]["candidates"][0]
    assert c["gain_lcb"] > 0.1 and not c["safe"] and c["d_fpr_sel_ucb"] > w.params.eps_fpr
    ablated = run(w, ScriptedOp(build, max_rung=1), ControllerOptions(step_safety=False))
    assert ablated.k == 1 and ablated.steps[0]["candidates"][0]["safe_strict"] is False


def test_argmax_is_over_safe_candidates_and_unsafe_classes_leave_the_active_set(world, monkeypatch):
    w = world
    monkeypatch.setattr(ctl, "compute_residual_sets", lambda *a, **k: ResidualSets((1, 2), ()))
    inc = w.inc_table.copy()
    inc[w.truth == 1] = 0                           # the incumbent / theta_R recognise neither class
    w.inc = FakeModel(inc)
    monkeypatch.setattr(ctl, "CandidateBuilder", lambda params, seed: types.SimpleNamespace(
        build=lambda view, extra=None: FakeModel(inc)))

    def build(doses):
        t = inc.copy()
        if doses.get(1):
            t[w.truth == 1] = 1                      # big gain ...
            t = _flip_benign(w, t, 30)               # ... but unsafe (benign rows flagged)
        if doses.get(2):
            t[np.flatnonzero(w.truth == 2)] = 2      # smaller gain, safe
        return t

    out = run(w, ScriptedOp(build, max_rung={1: 1, 2: 1}))
    first = {c["c"]: c for c in out.steps[0]["candidates"]}
    assert first[1]["gain_lcb"] > 0 and not first[1]["safe"] and first[2]["safe"]
    assert out.steps[0]["accepted"] == 2 and out.doses == {2: 1}
    assert all(1 not in s["active"] for s in out.steps[1:]) or len(out.steps) == 1


def test_step_bounds_use_alpha_over_k_max(world, monkeypatch):
    seen = []
    real_lcb, real_ucb = ctl.lcb, ctl.ucb
    monkeypatch.setattr(ctl, "lcb", lambda x, a: (seen.append(a), real_lcb(x, a))[1])
    monkeypatch.setattr(ctl, "ucb", lambda x, a: (seen.append(a), real_ucb(x, a))[1])
    run(world, ScriptedOp(improving(world, [0.0, 0.5]), max_rung=1))
    assert seen and set(seen) == {world.params.alpha / world.params.k_max}


def test_ablation_no_step_test_ranks_by_point_gain(world):
    one_row = lambda d: world.recognise(world.inc_table, world.cls2_sel[:1])   # one sel row only
    out = run(world, ScriptedOp(one_row, max_rung=1), ControllerOptions(step_test=False))
    assert out.k == 1                                  # a tiny positive point gain is accepted
    strict = run(world, ScriptedOp(one_row, max_rung=1))
    assert strict.k == 0 and strict.stop_reason == "no_gain"      # ... but not by LCB > eta


# ------------------------------------------------------------------ isolation from promotion evidence
def test_search_never_reads_gate_or_s_gate(world):
    w = world
    # Poison the VALUES of the promotion evidence. Label COUNTS stay (permuted labels): the frozen
    # measurability rule M needs support >= s_min in both D_sel and D_gate, so counts may matter.
    r = np.random.default_rng(0)
    poisoned = replace(w.view, gate_X=w.view.gate_X * 0 - 7.0, gate_y=r.permutation(w.view.gate_y),
                       s_gate_X=w.view.s_gate_X * 0 - 7.0, s_gate_y=r.permutation(w.view.s_gate_y))
    mk = lambda: ScriptedOp(improving(w, [0.0, 0.4, 0.8, 0.8]), max_rung=3)
    a = InterventionController(mk()).run(w.view, w.inc, w.ctx, anchor=w.inc)
    b = InterventionController(mk()).run(poisoned, w.inc, w.ctx, anchor=w.inc)
    assert json.dumps(a.steps, default=str) == json.dumps(b.steps, default=str)
    assert (a.k, a.doses, a.stop_reason) == (b.k, b.doses, b.stop_reason)


# ------------------------------------------------------------------ operators on a real learner
def _params():
    return make_params(rf_n_estimators=25, n_boot=300)


def test_data_operator_doses_are_nested_prefixes_bounded_and_deterministic():
    view = make_learnable_view(real_counts={0: 60, 1: 60, 2: 8})
    p = _params()
    ctx = DecisionContext(t=3, seed=4, params=p, anchor=None)
    builder = CandidateBuilder(p, 4)

    def mk():
        op = DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator())
        op.prepare(view, builder, None, (2,), p, ctx)
        return op

    op, op2 = mk(), mk()
    assert np.array_equal(op.pools[2], op2.pools[2])                 # same (seed, t, class) stream
    ms = [op.m(2, r) for r in range(len(p.rho_ladder))]
    assert ms == [0, 4, 8, 16, 32, 64] and all(a <= b for a, b in zip(ms, ms[1:]))
    assert np.array_equal(op.pools[2][:8], op.pools[2][:16][:8])     # prefix property
    assert op.next_dose(2, {}) == 1 and op.next_dose(2, {2: 5}) is None
    capped = replace(p, m_cap=10)
    op3 = DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator())
    op3.prepare(view, builder, None, (2,), capped, ctx)
    assert max(op3.m(2, r) for r in range(6)) == 10


def test_synthetic_share_cap_blocks_steps_that_exceed_phi_max():
    view = make_learnable_view(real_counts={0: 60, 1: 60, 2: 8})        # |D_real| = 128
    p = _params()
    ctx = DecisionContext(t=3, seed=4, params=p, anchor=None)
    op = DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator())
    op.prepare(view, CandidateBuilder(p, 4), None, (2,), p, ctx)
    assert op.feasible({2: 5}) and op.n_syn({2: 5}) == 64                # 64 / (128 + 64) = 0.33
    many = DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator())
    many.prepare(view, CandidateBuilder(p, 4), None, (0, 1), p, ctx)
    assert many.feasible({0: 1}) and not many.feasible({0: 5})          # 480 / (128 + 480) > 0.5
    assert not many.feasible({0: 3, 1: 3})


def test_rho_zero_candidate_equals_theta_R_and_synthetic_rows_never_enter_the_view():
    view = make_learnable_view(real_counts={0: 60, 1: 60, 2: 8})
    p = _params()
    ctx = DecisionContext(t=3, seed=4, params=p, anchor=None)
    builder = CandidateBuilder(p, 4)
    theta_R = builder.build(view)
    op = DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator())
    op.prepare(view, builder, theta_R, (2,), p, ctx)
    probe = np.random.default_rng(1).normal(size=(200, 4)).astype(np.float32) * 5
    assert np.array_equal(op.build({}).predict(probe), theta_R.predict(probe))
    assert np.array_equal(op.build({2: 0}).predict(probe), theta_R.predict(probe))
    m = op.build({2: 2})
    assert m.n_train_rows == theta_R.n_train_rows + op.m(2, 2)
    assert len(view.real_y) == 128                                       # D_real untouched
    assert op.describe({2: 2})["per_class"]["2"]["m"] == op.m(2, 2)


def test_real_controller_end_to_end_is_deterministic(monkeypatch):
    view = make_learnable_view(real_counts={0: 60, 1: 60, 2: 8})
    p = _params()
    base = CandidateBuilder(p, 4).build_base(view)
    ctx = DecisionContext(t=3, seed=4, params=p, anchor=base)
    monkeypatch.setattr(ctl, "compute_residual_sets", lambda *a, **k: ResidualSets((2,), ()))
    mk = lambda: InterventionController(DataOperator("SMOTE", lambda c, v, pr: SMOTEGenerator()))
    a, b = mk().run(view, base, ctx, anchor=base), mk().run(view, base, ctx, anchor=base)
    assert a.eligible == (2,) and a.region
    assert json.dumps(a.steps, default=str) == json.dumps(b.steps, default=str)
    assert (a.k, a.doses, a.stop_reason) == (b.k, b.doses, b.stop_reason)
    assert a.stop_reason in ctl.STOP_REASONS


# ------------------------------------------------------------------ threshold operator
def test_thresh_with_unit_weights_is_bit_identical_to_theta_R_and_weights_shift_decisions():
    view = make_learnable_view()
    p = _params()
    theta_R = CandidateBuilder(p, 0).build(view)
    probe = np.random.default_rng(2).normal(size=(300, 4)).astype(np.float32) * 5
    unit = ThreshModel(theta_R, {0: 1.0, 1: 1.0, 2: 1.0})
    assert np.array_equal(unit.predict(probe), theta_R.predict(probe))
    assert np.allclose(unit.predict_proba(probe).sum(axis=1), 1.0)
    heavy = ThreshModel(theta_R, {2: 1e6})
    assert (heavy.predict(probe) == 2).mean() > (theta_R.predict(probe) == 2).mean()
    op = ThresholdOperator()
    op.prepare(view, None, theta_R, (2,), p, DecisionContext(t=1, seed=0, params=p))
    assert op.next_dose(2, {}) == 1 and op.next_dose(2, {2: len(WEIGHT_LADDER) - 1}) is None
    assert op.build({2: 2}).weights == {2: WEIGHT_LADDER[2]}


def test_rng_purposes_are_distinct_and_deterministic():
    ctx = DecisionContext(t=5, seed=3, params=make_params())
    purposes = [ctl.PURPOSE_REGION, ctl.PURPOSE_ELIGIBLE, ctl.PURPOSE_POOL, ctl.PURPOSE_STEP,
                ctl.PURPOSE_PROMOTE_STAR, ctl.PURPOSE_PROMOTE_REAL, ctl.PURPOSE_CANARY, 34]
    assert len(set(purposes)) == len(purposes)
    a, b = sub_rng(ctx, 31, 2).random(), sub_rng(ctx, 31, 2).random()
    assert a == b and sub_rng(ctx, 31, 3).random() != a
