"""Promotion rule tests (SPEC v1.1 J.1 item 2, D2, D3) on hand-built views with scripted models.

Rows are identified by id: X = [[id, 0]], and a FakeModel answers from a per-id prediction
table, so each test controls exactly which rows each model gets right.
"""
from dataclasses import fields, replace

import numpy as np
import pytest

from proteus.intervention.params import InterventionParams
from proteus.intervention.promotion import (
    REASONS, evaluate_candidate, promote, sanity_check)
from proteus.intervention.protocol import ControllerView

NAMES = ("benign", "a", "b")     # b is the drift class
K = 3
REGION = (2,)

SEGMENTS = {                      # class -> row count
    "ref": {0: 150, 1: 150},
    "real": {0: 40, 1: 40, 2: 40},
    "sel": {0: 100, 1: 30, 2: 40},
    "gate": {0: 100, 1: 30, 2: 40},
    "s_sel": {0: 150, 1: 60},
    "s_gate": {0: 150, 1: 60},
}


def make_params(**kw):
    return InterventionParams(benign_label="benign", **kw)


class FakeModel:
    """Answers from a table indexed by the row id in column 0 of X."""

    def __init__(self, table, proba="onehot", n_classes=K):
        self.table = np.asarray(table, dtype=np.int64)
        self.classes_ = np.arange(n_classes)
        self.proba = proba
        self.n_classes = n_classes

    def predict(self, X):
        return self.table[np.asarray(X)[:, 0].astype(np.int64)]

    def predict_proba(self, X):
        p = np.eye(self.n_classes)[self.predict(X)]
        if self.proba == "nan":
            p[:] = np.nan
        elif self.proba == "unnormalised":
            p = p * 2.0
        return p


def make_view(segments=None):
    """Returns (view, truth_by_id, ranges) with ids assigned segment by segment."""
    segments = segments or SEGMENTS
    truth, ranges, arrays = [], {}, {}
    for name, counts in segments.items():
        y = np.concatenate([np.full(n, c, dtype=np.int64) for c, n in counts.items()]) \
            if counts else np.empty(0, dtype=np.int64)
        start = len(truth)
        truth.extend(y.tolist())
        ranges[name] = (start, len(truth))
        ids = np.arange(start, len(truth), dtype=np.float32)
        arrays[name] = (np.stack([ids, np.zeros_like(ids)], axis=1), y)
    view = ControllerView(
        ref_X=arrays["ref"][0], ref_y=arrays["ref"][1],
        real_X=arrays["real"][0], real_y=arrays["real"][1],
        sel_X=arrays["sel"][0], sel_y=arrays["sel"][1],
        gate_X=arrays["gate"][0], gate_y=arrays["gate"][1],
        s_sel_X=arrays["s_sel"][0], s_sel_y=arrays["s_sel"][1],
        s_gate_X=arrays["s_gate"][0], s_gate_y=arrays["s_gate"][1], class_names=NAMES)
    return view, np.array(truth, dtype=np.int64), ranges


@pytest.fixture()
def world():
    view, truth, ranges = make_view()
    incumbent_table = truth.copy()
    incumbent_table[truth == 2] = 0            # incumbent never recognises the drift class
    good_table = truth.copy()                  # candidate recognises everything
    return view, truth, ranges, FakeModel(incumbent_table), good_table


def _rows(ranges, truth, seg, cls):
    lo, hi = ranges[seg]
    return lo + np.flatnonzero(truth[lo:hi] == cls)


def _promote(view, incumbent, table, params=None, seed=0, region=REGION, anchor=None):
    """At drift onset the incumbent IS the anchor, so that is the default."""
    return promote(view, incumbent, FakeModel(table), region, params or make_params(),
                   np.random.default_rng(seed), incumbent if anchor is None else anchor)


# ----------------------------------------------------------------------------- core rule
def test_valid_candidate_is_promoted(world):
    view, truth, ranges, inc, good = world
    d = _promote(view, inc, good)
    assert d.promoted and d.reason == "promoted"
    assert d.report.failed == ()
    assert d.report.utility_gain_lcb > 0.5 and d.report.utility_gain_point == pytest.approx(1.0)
    assert d.model is not inc


def test_candidate_without_region_improvement_is_rejected(world):
    view, truth, ranges, inc, good = world
    d = _promote(view, inc, np.asarray(inc.table).copy())
    assert not d.promoted and d.reason == "utility_no_gain"
    assert d.model is inc
    assert d.report.utility_gain_point == pytest.approx(0.0)


def test_a_one_row_improvement_is_not_significant(world):
    view, truth, ranges, inc, good = world
    table = np.asarray(inc.table).copy()
    table[_rows(ranges, truth, "gate", 2)[0]] = 2
    d = _promote(view, inc, table)
    assert d.report.utility_gain_point > 0
    assert not d.promoted and d.reason == "utility_inconclusive"


def test_candidate_that_harms_stable_traffic_is_rejected(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    stable_a = _rows(ranges, truth, "s_gate", 1)
    table[stable_a[: int(0.4 * len(stable_a))]] = 0
    d = _promote(view, inc, table)
    assert d.report.utility_ok                          # drift side is fine ...
    assert not d.promoted and d.reason == "envelope_violated"   # ... but stable traffic is hurt
    assert not d.report.stable_f1_ok and "stable_f1" in d.report.failed
    assert d.model is inc


def test_candidate_that_raises_benign_fpr_on_current_traffic_is_rejected(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    benign_gate = _rows(ranges, truth, "gate", 0)
    table[benign_gate[: int(0.2 * len(benign_gate))]] = 1
    d = _promote(view, inc, table)
    assert d.report.utility_ok
    assert not d.promoted and d.reason == "envelope_violated"
    assert not d.report.fpr_current_ok and d.report.stable_f1_ok


def test_candidate_that_raises_benign_fpr_on_stable_traffic_is_rejected(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    benign_s = _rows(ranges, truth, "s_gate", 0)
    table[benign_s[: int(0.1 * len(benign_s))]] = 1
    d = _promote(view, inc, table)
    assert not d.promoted and d.reason == "envelope_violated"
    assert not d.report.fpr_stable_ok


def test_empty_region_does_nothing(world):
    view, truth, ranges, inc, good = world
    d = _promote(view, inc, good, region=())
    assert not d.promoted and d.reason == "no_affected_region" and d.report is None
    assert d.model is inc


def test_thresholds_come_from_params(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    benign_s = _rows(ranges, truth, "s_gate", 0)
    table[benign_s[: int(0.1 * len(benign_s))]] = 1
    assert not _promote(view, inc, table).promoted
    lenient = make_params(eps_fpr=0.5, eps_s=0.5)
    assert _promote(view, inc, table, params=lenient).promoted


# ----------------------------------------------------------------------------- D3: taxonomy
def test_every_reason_label_is_reachable_and_valid(world):
    view, truth, ranges, inc, good = world
    seen = {}

    def record(decision):
        assert decision.reason in REASONS
        seen[decision.reason] = decision

    record(_promote(view, inc, good))                                           # promoted
    record(_promote(view, inc, good, region=()))                                # no_affected_region
    record(promote(view, inc, FakeModel(good, proba="nan"), REGION, make_params(),
                   np.random.default_rng(0), inc))                              # sanity
    record(_promote(view, inc, np.asarray(inc.table).copy()))                   # utility_no_gain
    one = np.asarray(inc.table).copy()
    one[_rows(ranges, truth, "gate", 2)[0]] = 2
    record(_promote(view, inc, one))                                            # utility_inconclusive

    empty_gate = make_view(dict(SEGMENTS, gate={}))
    v, t, r = empty_gate
    inc_t = t.copy()
    inc_t[t == 2] = 0
    record(_promote(v, FakeModel(inc_t), t.copy()))                             # utility_unmeasurable

    no_benign = make_view(dict(SEGMENTS, s_gate={1: 60}))
    v, t, r = no_benign
    inc_t = t.copy()
    inc_t[t == 2] = 0
    record(_promote(v, FakeModel(inc_t), t.copy()))                             # envelope_unverifiable

    harm = good.copy()
    harm[_rows(ranges, truth, "s_gate", 0)[:15]] = 1
    record(_promote(view, inc, harm))                                           # envelope_violated

    # envelope_inconclusive: the point estimates are zero (anchor and candidate each make exactly
    # one different benign error on S_gate) but the paired bootstrap cannot rule out a rise.
    benign_s = _rows(ranges, truth, "s_gate", 0)
    anchor_table = np.asarray(inc.table).copy()
    anchor_table[benign_s[0]] = 1
    cand_table = good.copy()
    cand_table[benign_s[1]] = 1
    record(_promote(view, inc, cand_table, anchor=FakeModel(anchor_table)))     # envelope_inconclusive

    assert set(seen) == set(REASONS), f"unreached reasons: {set(REASONS) - set(seen)}"
    assert seen["envelope_inconclusive"].report.delta_fpr_stable_point == pytest.approx(0.0)
    assert seen["envelope_inconclusive"].report.delta_fpr_stable_ucb > 0.005
    assert seen["utility_unmeasurable"].report.utility_status == "unmeasurable"
    assert all(not seen[r].promoted for r in REASONS if r != "promoted")
    assert seen["promoted"].promoted


def test_unverifiable_safety_fails_closed():
    segs = dict(SEGMENTS, s_gate={1: 60})            # no benign rows in S_gate
    view, truth, ranges = make_view(segs)
    inc_table = truth.copy()
    inc_table[truth == 2] = 0
    d = _promote(view, FakeModel(inc_table), truth.copy())
    assert d.report.utility_ok
    assert not d.promoted and d.reason == "envelope_unverifiable"
    assert np.isnan(d.report.delta_fpr_stable_ucb) and not d.report.fpr_stable_ok
    assert d.report.n_s_gate_benign == 0

    segs = dict(SEGMENTS, s_gate={})                 # no stable evidence at all
    view, truth, ranges = make_view(segs)
    inc_table = truth.copy()
    inc_table[truth == 2] = 0
    d = _promote(view, FakeModel(inc_table), truth.copy())
    assert not d.promoted and d.reason == "envelope_unverifiable"


def test_a_known_violation_outranks_missing_evidence():
    segs = dict(SEGMENTS, s_gate={1: 60})            # fpr_stable unverifiable (no benign) ...
    view, truth, ranges = make_view(segs)
    inc_table = truth.copy()
    inc_table[truth == 2] = 0
    table = truth.copy()
    table[_rows(ranges, truth, "s_gate", 1)[:30]] = 0   # ... and stable F1 clearly violated
    d = _promote(view, FakeModel(inc_table), table)
    assert d.report.stable_f1_status == "violated"
    assert d.report.fpr_stable_status == "unverifiable"
    assert d.reason == "envelope_violated"
    assert set(d.report.failed) >= {"stable_f1", "fpr_stable"}


def test_sanity_failures_are_rejected_before_any_statistics(world):
    view, truth, ranges, inc, good = world
    for mode in ("nan", "unnormalised"):
        d = promote(view, inc, FakeModel(good, proba=mode), REGION, make_params(),
                    np.random.default_rng(0), inc)
        assert not d.promoted and d.reason == "sanity"
        assert d.report.failed == ("sanity",) and d.report.utility_status == "not_evaluated"
    ok, msg = sanity_check(FakeModel(good), 2, K)
    assert ok and msg == "ok"
    ok, _ = sanity_check(FakeModel(good), 2, 2)          # classes (up to 2) outside the range
    assert not ok


def test_report_carries_the_support_counts(world):
    view, truth, ranges, inc, good = world
    r = _promote(view, inc, good).report
    assert r.n_gate_rows == 170 and r.gate_support == (100, 30, 40)
    assert r.n_gate_region_rows == 40 and r.n_gate_benign == 100
    assert r.n_s_gate_rows == 210 and r.s_gate_support == (150, 60, 0)
    assert r.n_s_gate_benign == 150 and r.n_stable_classes == 2


# ----------------------------------------------------------------------------- D2: anchor
def test_anchor_blocks_cumulative_stable_degradation():
    """Each candidate costs ~0.6 eps of benign FPR relative to its predecessor. Measured against
    the moving incumbent every step looks safe (the ratchet); against the fixed anchor the second
    step is correctly rejected."""
    segs = {"ref": {0: 150, 1: 150}, "real": {0: 40, 1: 40, 2: 40},
            "sel": {0: 100, 1: 30, 2: 400}, "gate": {0: 100, 1: 30, 2: 400},
            "s_sel": {0: 150, 1: 60}, "s_gate": {0: 20000, 1: 10000}}
    view, truth, ranges = make_view(segs)
    base_table = truth.copy()
    base_table[truth == 2] = 0
    anchor = FakeModel(base_table)

    gate_b = _rows(ranges, truth, "gate", 2)
    s_benign = _rows(ranges, truth, "s_gate", 0)

    t1 = truth.copy()                      # fixes half of class b, costs 60 benign rows (0.003)
    t1[gate_b[200:]] = 0
    t1[s_benign[:60]] = 1
    cand1 = FakeModel(t1)
    d1 = promote(view, anchor, cand1, REGION, make_params(), np.random.default_rng(0), anchor)
    assert d1.promoted, d1.report

    t2 = truth.copy()                      # fixes all of class b, costs 120 benign rows (0.006)
    t2[s_benign[:120]] = 1
    cand2 = FakeModel(t2)
    moving = promote(view, cand1, cand2, REGION, make_params(), np.random.default_rng(0), cand1)
    assert moving.promoted, "against the moving incumbent the second step looks safe (ratchet)"
    anchored = promote(view, cand1, cand2, REGION, make_params(), np.random.default_rng(0), anchor)
    # still rejected against the anchor. v1.3: the point estimate (0.006 > eps 0.005) no longer
    # decides the label; the lower bound (0.00495) does not exceed eps, so the violation is not
    # statistically established and the reason is envelope_inconclusive, not envelope_violated.
    assert not anchored.promoted and anchored.reason == "envelope_inconclusive"
    assert anchored.report.utility_ok
    assert anchored.report.delta_fpr_stable_point == pytest.approx(0.006)
    assert anchored.report.delta_fpr_stable_lcb <= 0.005 < anchored.report.delta_fpr_stable_ucb
    assert not anchored.report.fpr_stable_ok

    t3 = truth.copy()                      # costs 240 benign rows (0.012): clearly established
    t3[s_benign[:240]] = 1
    worse = promote(view, cand1, FakeModel(t3), REGION, make_params(), np.random.default_rng(0),
                    anchor)
    assert not worse.promoted and worse.reason == "envelope_violated"
    assert worse.report.delta_fpr_stable_lcb > 0.005


def test_anchor_is_required(world):
    view, truth, ranges, inc, good = world
    with pytest.raises(ValueError):
        evaluate_candidate(view, inc, FakeModel(good), REGION, make_params(),
                           np.random.default_rng(0), None)


def test_utility_is_measured_against_the_incumbent_not_the_anchor(world):
    view, truth, ranges, inc, good = world
    already_fixed = FakeModel(good)          # incumbent already recognises class b
    anchor = inc                             # the anchor does not
    d = promote(view, already_fixed, FakeModel(good), REGION, make_params(),
                np.random.default_rng(0), anchor)
    assert not d.promoted and d.reason == "utility_no_gain"    # no gain over what is deployed
    assert d.report.utility_gain_point == pytest.approx(0.0)


# ----------------------------------------------------------------------------- purity / bounds
def test_promotion_is_deterministic_for_a_fixed_rng_seed(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    table[_rows(ranges, truth, "gate", 0)[:3]] = 1
    a = evaluate_candidate(view, inc, FakeModel(table), REGION, make_params(),
                           np.random.default_rng(11), inc)
    b = evaluate_candidate(view, inc, FakeModel(table), REGION, make_params(),
                           np.random.default_rng(11), inc)
    assert a == b or (str(a) == str(b))      # nan != nan under dataclass equality


def test_promotion_never_reads_selection_or_training_buffers(world):
    view, truth, ranges, inc, good = world
    base = _promote(view, inc, good)

    class Audited(ControllerView):
        log = []

        def __getattribute__(self, name):
            if name in ControllerView.__dataclass_fields__:
                Audited.log.append(name)
            return super().__getattribute__(name)

    audited = Audited(**{f.name: getattr(view, f.name) for f in fields(view)})
    Audited.log.clear()
    d = promote(audited, inc, FakeModel(good), REGION, make_params(), np.random.default_rng(0),
                inc)
    assert d.promoted
    touched = set(Audited.log)
    assert touched.isdisjoint({"sel_X", "sel_y", "s_sel_X", "s_sel_y", "real_X", "real_y"}), \
        f"promotion read fields it must not: {sorted(touched)}"
    assert touched <= {"ref_X", "ref_y", "gate_X", "gate_y", "s_gate_X", "s_gate_y",
                       "class_names"}
    scrambled = replace(view, sel_y=np.zeros_like(view.sel_y), s_sel_y=np.zeros_like(view.s_sel_y),
                        real_y=np.zeros_like(view.real_y))
    assert str(_promote(scrambled, inc, good).report) == str(base.report)


def test_promotion_rejects_anything_that_is_not_a_controller_view(world):
    view, truth, ranges, inc, good = world
    with pytest.raises(TypeError):
        promote({"gate_X": view.gate_X}, inc, FakeModel(good), REGION, make_params(),
                np.random.default_rng(0), inc)
    with pytest.raises(TypeError):
        evaluate_candidate(None, inc, FakeModel(good), REGION, make_params(),
                           np.random.default_rng(0), inc)


# ------------------------------------------------------------------ v1.3: violated needs an LCB > eps
from proteus.intervention.promotion import _envelope_status  # noqa: E402

ENVELOPE = ("stable_f1_status", "fpr_stable_status", "fpr_current_status")


def _small_benign_world(n_benign_gate=30):
    """The B=25 smoke situation: only ~30 benign rows in D_gate."""
    segs = dict(SEGMENTS, gate={0: n_benign_gate, 1: 30, 2: 40})
    view, truth, ranges = make_view(segs)
    inc_table = truth.copy()
    inc_table[truth == 2] = 0
    return view, truth, ranges, FakeModel(inc_table)


def test_envelope_status_truth_table():
    eps = 0.005
    nan = float("nan")
    assert _envelope_status(0.001, 0.004, eps) == "ok"             # UCB <= eps: safe
    assert _envelope_status(0.2, 0.004, eps) == "ok"               # UCB decides ok, whatever the LCB
    assert _envelope_status(0.006, 0.02, eps) == "violated"        # LCB > eps: established
    assert _envelope_status(0.005, 0.02, eps) == "inconclusive"    # LCB == eps is not > eps
    assert _envelope_status(-0.03, 0.12, eps) == "inconclusive"    # cannot decide either way
    assert _envelope_status(nan, 0.02, eps) == "inconclusive"      # UCB defined, LCB not
    assert _envelope_status(0.9, nan, eps) == "unverifiable"       # undefined UCB fails closed
    assert _envelope_status(nan, nan, eps) == "unverifiable"
    assert _envelope_status(0.005, 0.005, eps) == "ok"             # boundary: UCB == eps passes


def test_genuinely_established_violation_is_labelled_violated(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    benign_gate = _rows(ranges, truth, "gate", 0)
    table[benign_gate[: int(0.2 * len(benign_gate))]] = 1           # 20 of 100 benign rows flipped
    r = _promote(view, inc, table).report
    assert r.fpr_current_status == "violated"
    assert r.delta_fpr_current_lcb > r.eps_fpr                      # the bound itself exceeds eps
    assert r.delta_fpr_current_point == pytest.approx(0.2)
    assert r.n_gate_benign == 100


def test_small_sample_unresolved_case_is_inconclusive_not_violated():
    """One flipped benign row among 30: the point estimate (3.3 pp) is ~7x eps, which v1.2 called
    'violated'. The data cannot establish a degradation beyond eps, so v1.3 says inconclusive."""
    view, truth, ranges, inc = _small_benign_world(30)
    good = truth.copy()
    good[_rows(ranges, truth, "gate", 0)[0]] = 1                    # exactly one benign row flipped
    d = _promote(view, inc, good)
    r = d.report
    assert r.n_gate_benign == 30 and r.utility_ok
    assert r.delta_fpr_current_point == pytest.approx(1 / 30)       # > eps: the old v1.2 trigger
    assert r.delta_fpr_current_point > r.eps_fpr
    assert r.delta_fpr_current_lcb <= r.eps_fpr < r.delta_fpr_current_ucb
    assert r.fpr_current_status == "inconclusive"
    assert not d.promoted and d.reason == "envelope_inconclusive"   # still rejected


def test_clearly_safe_case_passes_and_is_promoted(world):
    view, truth, ranges, inc, good = world
    d = _promote(view, inc, good)
    r = d.report
    assert d.promoted and d.reason == "promoted"
    assert all(getattr(r, s) == "ok" for s in ENVELOPE)
    assert r.delta_stable_f1_ucb <= r.eps_stable_f1
    assert r.delta_fpr_stable_ucb <= r.eps_fpr and r.delta_fpr_current_ucb <= r.eps_fpr


def test_report_carries_raw_quantities_bounds_epsilon_and_level(world):
    view, truth, ranges, inc, good = world
    table = good.copy()
    table[_rows(ranges, truth, "s_gate", 0)[:15]] = 1
    r = _promote(view, inc, table).report
    p = make_params()
    assert (r.eps_stable_f1, r.eps_fpr, r.envelope_alpha) == (p.eps_s, p.eps_fpr, p.promotion_alpha)
    assert (r.n_s_gate_benign, r.n_s_gate_rows, r.n_gate_benign, r.n_stable_classes) == \
        (150, 210, 100, 2)
    for point, lo, hi in (("delta_stable_f1_point", "delta_stable_f1_lcb", "delta_stable_f1_ucb"),
                          ("delta_fpr_stable_point", "delta_fpr_stable_lcb", "delta_fpr_stable_ucb"),
                          ("delta_fpr_current_point", "delta_fpr_current_lcb", "delta_fpr_current_ucb")):
        assert getattr(r, lo) <= getattr(r, hi)
        assert getattr(r, lo) - 1e-9 <= getattr(r, point) <= getattr(r, hi) + 1e-9
    from proteus.intervention.serialize import dumps_strict
    text = dumps_strict(r)                                          # all of it survives serialisation
    assert "delta_fpr_stable_lcb" in text and "envelope_alpha" in text


def test_sanity_failure_still_reports_epsilon_and_level(world):
    view, truth, ranges, inc, good = world
    bad = promote(view, inc, FakeModel(good, proba="nan"), REGION, make_params(),
                  np.random.default_rng(0), inc)
    assert bad.reason == "sanity" and bad.report.eps_fpr == make_params().eps_fpr


def test_relabelling_never_changes_a_promotion_decision(world):
    """Sweep harms from none to heavy. Promotion must equal 'utility ok and every UCB <= eps' (the
    unchanged rule), and the v1.2 point-estimate rule differs from v1.3 only in the
    violated/inconclusive split, never in ok vs not-ok."""
    view, truth, ranges, inc, good = world
    p = make_params()
    benign_s = _rows(ranges, truth, "s_gate", 0)
    benign_g = _rows(ranges, truth, "gate", 0)
    saw_split = False
    for n_s in (0, 1, 3, 10, 40):
        for n_g in (0, 1, 3, 10, 40):
            table = good.copy()
            table[benign_s[:n_s]] = 1
            table[benign_g[:n_g]] = 1
            d = _promote(view, inc, table)
            r = d.report
            ucb_pass = (r.delta_stable_f1_ucb <= p.eps_s and r.delta_fpr_stable_ucb <= p.eps_fpr
                        and r.delta_fpr_current_ucb <= p.eps_fpr)
            assert d.promoted == (r.utility_ok and ucb_pass)
            for status, point, ucb_, lcb_, eps in (
                    (r.stable_f1_status, r.delta_stable_f1_point, r.delta_stable_f1_ucb,
                     r.delta_stable_f1_lcb, p.eps_s),
                    (r.fpr_stable_status, r.delta_fpr_stable_point, r.delta_fpr_stable_ucb,
                     r.delta_fpr_stable_lcb, p.eps_fpr),
                    (r.fpr_current_status, r.delta_fpr_current_point, r.delta_fpr_current_ucb,
                     r.delta_fpr_current_lcb, p.eps_fpr)):
                v12 = "ok" if ucb_ <= eps else ("violated" if point > eps else "inconclusive")
                assert (status == "ok") == (v12 == "ok")            # pass/fail identical to v1.2
                if status != v12:                                   # only the split may move ...
                    assert {status, v12} == {"violated", "inconclusive"}
                    assert v12 == "violated" and status == "inconclusive"   # ... and only downwards
                    saw_split = True
                if status == "violated":
                    assert lcb_ > eps
    assert saw_split, "the sweep should include at least one small-sample case v1.2 over-called"
