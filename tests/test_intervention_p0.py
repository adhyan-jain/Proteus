"""P0 tooling tests (SPEC v1.2 section L.1): positive control, validity, data adequacy, diagnostics,
outcome state machine, runner contract, provenance, determinism, information boundaries.

Synthetic fixture only (the real-data cache is NOT built here). The fixture has duplicate rows
within and across days, so group-level audits are non-trivial.
"""
import ast
import itertools
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import proteus.intervention.p0 as p0
import proteus.intervention.validity as validity
from proteus.intervention.cache import DataBundle, hash_rows
from proteus.intervention.conditions import (
    LABEL_REGIME_ALL_NON_E, LABEL_REGIME_BUDGET, DecisionContext, Frozen, Outcome, RealOnly,
    RealOnlyAllLabels)
from proteus.intervention.learner import CandidateBuilder, compute_affected_region
from proteus.intervention.params import InterventionParams
from proteus.intervention.promotion import REASONS
from proteus.intervention.protocol import (
    ControllerView, ScenarioConfig, SPEC_VERSION, StreamReplay, _role_of_groups, build_partitions)
from proteus.intervention.serialize import loads_strict
from proteus.intervention.validity import (
    OUTCOMES, STATUSES, P0Criteria, SPEC_PATH, budget_status, check_v1, check_v2, check_v4,
    decide_outcome, evaluate_p0, scope_statement, spec_rules_sha256, spec_rules_text)
from tests.test_intervention_protocol import N_CROSS_PLANTED, _make_data

CFG = ScenarioConfig("T", ("Monday", "Tuesday", "Wednesday", "Thursday"), ("Friday",),
                     window_size=600, n_pre_windows=2, n_post_windows=5, budget=100,
                     s_size=400, ref_size=500, real_buffer_cap=400, eval_buffer_cap=400)
PARAMS = InterventionParams(benign_label="c0", rf_n_estimators=15, n_boot=200)   # speed only
SEEDS = (0, 1)
BUDGETS = (30, 100)


@pytest.fixture(scope="module")
def data():
    return _make_data()


@pytest.fixture(scope="module")
def manifest(data):
    return build_partitions(data, CFG, seed=0)


@pytest.fixture(scope="module")
def run(data, tmp_path_factory):
    out = tmp_path_factory.mktemp("p0_out")
    result = p0.run_p0(data, budgets=BUDGETS, seeds=SEEDS, params=PARAMS, scenario_cfg=CFG,
                       out_dir=out)
    return result, out


def _full_view(data, manifest):
    state = p0.TrackedState(data, manifest)
    for step in StreamReplay(manifest):
        state.ingest(step)
    return state.view()


# --------------------------------------------------------------------- positive control
def test_all_labels_stream_is_a_superset_of_the_budget_stream_on_the_same_manifest(data, manifest):
    budget = list(StreamReplay(manifest))
    allv = list(p0.all_labels_steps(data, manifest))
    assert [s.t for s in budget] == [s.t for s in allv]
    e_rows = np.concatenate([w.e_idx for w in manifest.windows])
    forbidden = np.concatenate([e_rows, manifest.s_report_idx, manifest.s_cal_idx])
    for b, a, prev in zip(budget, allv, [None] + list(manifest.windows[:-1])):
        assert set(b.arrived_idx.tolist()) <= set(a.arrived_idx.tolist())
        assert not np.isin(a.arrived_idx, forbidden).any()          # E_t / S_report / S_cal never
        if prev is None:
            assert len(a.arrived_idx) == 0                          # label delay: nothing at t=0
        else:
            expected = np.concatenate([prev.l_idx, prev.u_idx])     # every non-E row of window t-1
            assert np.array_equal(a.arrived_idx, expected)
            n_b = len(prev.l_idx)
            assert np.array_equal(a.arrived_role[:n_b], b.arrived_role)   # same roles for the B rows
            # every labelled row, including the extra ones, is assigned by the same group hash
            assert np.array_equal(a.arrived_role,
                                  _role_of_groups(data.group[a.arrived_idx], manifest.seed))
        assert not np.intersect1d(a.arrived_idx, a.spec.l_idx).size       # nothing from window t


def test_positive_control_is_real_only_with_a_different_label_regime():
    pc = RealOnlyAllLabels()
    assert isinstance(pc, RealOnly) and pc.name == "REAL_ONLY_ALL_LABELS"
    assert RealOnlyAllLabels.decide is RealOnly.decide              # no private decision logic
    assert pc.label_regime == LABEL_REGIME_ALL_NON_E
    assert RealOnly.label_regime == Frozen.label_regime == LABEL_REGIME_BUDGET
    assert pc.is_positive_control and not getattr(RealOnly(), "is_positive_control", False)
    assert "never a headline" in RealOnlyAllLabels.__doc__ and "evict" in RealOnlyAllLabels.__doc__


def test_positive_control_decides_exactly_like_real_only_on_the_same_view(data, manifest):
    view = _full_view(data, manifest)
    base = CandidateBuilder(PARAMS, 0).build_base(view)
    ctx = DecisionContext(t=5, seed=0, params=PARAMS, anchor=base)
    a, b = RealOnly().decide(view, base, ctx), RealOnlyAllLabels().decide(view, base, ctx)
    assert (a.reason, a.region, a.eligible, a.promoted) == (b.reason, b.region, b.eligible,
                                                            b.promoted)


def test_positive_control_evicts_the_real_buffer_and_the_result_says_so(run):
    result, _ = run
    for b in BUDGETS:
        for rec in result["budget_files"][b]["runs"]:
            buf = rec["buffer"]
            if rec["condition"] == "REAL_ONLY_ALL_LABELS":
                assert rec["is_positive_control"] and buf["real_buffer_evicted"]
                assert buf["evicted_rows"]["real"] > 0 and buf["final_sizes"]["real"] == 400
                assert "FIFO" in buf["note"]
            else:
                assert not rec["is_positive_control"] and not buf["real_buffer_evicted"]


# ---------------------------------------------------------------------------- V1 audit
def test_v1_is_clean_on_the_fixture(run):
    result, _ = run
    v1 = result["summary"]["validity"]["v1_leakage_audit"]
    assert v1["pass"] and v1["n_run_violations"] == 0 and v1["n_manifest_violations"] == 0
    assert v1["n_budget_nesting_violations"] == 0
    assert v1["n_runs_audited"] == len(SEEDS) * len(BUDGETS) * 3


def test_v1_detects_planted_leaks(data, manifest):
    aud = p0.Auditor(data, manifest)
    state = p0.TrackedState(data, manifest)
    steps = list(StreamReplay(manifest))
    for step in steps[:4]:
        state.ingest(step)
    t = steps[3].t
    clean = aud.audit_view(state.provenance(), t, LABEL_REGIME_BUDGET)
    assert clean["n_violations"] == 0

    prov = state.provenance()
    e_rows = manifest.windows[2].e_idx
    leaked = {**prov, "real": np.concatenate([prov["real"], e_rows[:3]])}
    assert aud.audit_view(leaked, t, LABEL_REGIME_BUDGET)["n_row_overlap"] >= 3
    assert aud.audit_view(leaked, t, LABEL_REGIME_BUDGET)["n_violations"] > 0

    rep = {**prov, "s_gate": np.concatenate([prov["s_gate"], manifest.s_report_idx[:2]])}
    assert aud.audit_view(rep, t, LABEL_REGIME_BUDGET)["n_row_overlap"] >= 2

    unl = {**prov, "gate": np.concatenate([prov["gate"], manifest.windows[1].u_idx[:4]])}
    assert aud.audit_view(unl, t, LABEL_REGIME_BUDGET)["n_unlabelled_rows"] >= 4
    # ... which is legitimate labelled data in the positive control's regime
    assert aud.audit_view(unl, t, LABEL_REGIME_ALL_NON_E)["n_unlabelled_rows"] == 0

    fut = {**prov, "sel": np.concatenate([prov["sel"], manifest.windows[t].l_idx[:5]])}
    assert aud.audit_view(fut, t, LABEL_REGIME_BUDGET)["n_future_rows"] >= 5


def test_manifest_audit_is_clean_but_reports_cross_pool_duplicates_separately(data, manifest):
    audit = p0.Auditor(data, manifest).audit_manifest()
    assert audit["n_same_pool_group_overlaps"] == 0
    assert audit["n_window_row_reuse"] == 0 and audit["n_ref_rows_not_in_train"] == 0
    assert audit["n_cross_pool_group_overlaps"] > 0         # the fixture plants Monday rows on Friday
    assert audit["n_cross_pool_group_overlaps"] <= N_CROSS_PLANTED


def test_partition_rows_accessor_is_a_pure_view_of_the_manifest_and_leaves_the_digest_alone(
        data, manifest):
    parts = manifest.partition_rows()
    assert set(parts) == {"train", "ref", "s_cal", "s_sel", "s_gate", "s_report"}
    assert parts["train"] is manifest.train_idx and parts["ref"] is manifest.ref_idx
    assert parts["s_report"] is manifest.s_report_idx
    assert manifest.digest() == build_partitions(data, CFG, 0).digest()      # reproducible


# ----------------------------------------------------------------- nested budgets (scope)
def test_budgets_are_nested_on_a_matched_seed(data):
    small = build_partitions(data, replace(CFG, budget=30), 1)
    large = build_partitions(data, replace(CFG, budget=100), 1)
    audit = p0.audit_budget_nesting(small, large)
    assert audit["n_violations"] == 0 and audit["budgets"] == [30, 100]
    for ws, wl in zip(small.windows, large.windows):
        assert set(ws.l_idx.tolist()) <= set(wl.l_idx.tolist())          # B=30 rows inside B=100
        assert np.array_equal(ws.e_idx, wl.e_idx)


def test_nesting_audit_detects_broken_nesting(data):
    small = build_partitions(data, replace(CFG, budget=30), 1)
    large = build_partitions(data, replace(CFG, budget=100), 1)
    other_seed = build_partitions(data, replace(CFG, budget=100), 2)
    assert p0.audit_budget_nesting(small, other_seed)["n_violations"] > 0
    w = large.windows[0]
    tampered = replace(w, l_idx=w.l_idx[::-1].copy())
    bad = replace(large, windows=(tampered,) + tuple(large.windows[1:]))
    assert any("prefix" in p for p in p0.audit_budget_nesting(small, bad)["problems"])
    # a nesting violation fails V1 (partition integrity)
    recs = [{"condition": "FROZEN", "v1": {"n_violations": 0, "n_cross_pool_group_overlaps": 0}}]
    audits = [{"n_same_pool_group_overlaps": 0, "n_cross_pool_group_overlaps": 0}]
    assert check_v1(recs, audits, [{"n_violations": 0}])["pass"]
    assert not check_v1(recs, audits, [{"n_violations": 2}])["pass"]


# --------------------------------------------------------------------------- V2 diagnostic
def test_v2_matches_a_direct_region_computation_against_theta_base(run, data):
    result, _ = run
    for rec in result["budget_files"][100]["runs"]:
        if rec["condition"] != "FROZEN":
            continue
        seed = rec["seed"]
        t_last_pre = CFG.n_pre_windows - 1
        manifest = build_partitions(data, replace(CFG, budget=100), seed)
        state = p0.TrackedState(data, manifest)
        for step in StreamReplay(manifest):
            state.ingest(step)
            if step.t == t_last_pre:
                break
        view = state.view()
        base = CandidateBuilder(PARAMS, seed).build_base(view)
        info = compute_affected_region(
            view, base, PARAMS, DecisionContext(t_last_pre, seed, PARAMS).rng(
                p0._PURPOSE_FROZEN_DIAGNOSTIC))
        step_rec = [s for s in rec["steps"] if s["t"] == t_last_pre][0]
        assert step_rec["region"] == list(info.region)
        assert step_rec["measurable"] == list(info.measurable)
        v2 = result["summary"]["diagnostics"]["v2_null_region"]["per_budget"][100]["per_seed"][seed]
        assert v2["region"] == list(info.region) and v2["status"] == "evaluated"


# ----------------------------------------------------- synthetic records for the state machine
NK = 10                 # class count in the synthetic records
DRIFT = (7, 8)
CRIT = P0Criteria()
N_MIN, EPS_DEF = 5, 0.05
AUDITS = [{"n_same_pool_group_overlaps": 0, "n_cross_pool_group_overlaps": 0}]


def _step(t, region=(), measurable=(), eligible=None, reason="utility_no_gain", counts=None):
    return {"t": t, "phase": "post" if t >= 4 else "pre", "controller_active": t >= 4,
            "region": list(region), "measurable": list(measurable), "eligible": eligible,
            "reason": reason, "real_class_counts": list(counts or [10] * NK)}


def _rec(condition, seed, steps, budget=25, drift=DRIFT, violations=0, ambiguity=None):
    return {"condition": condition, "seed": seed, "budget": budget, "n_pre_windows": 4,
            "drift_classes": list(drift), "steps": steps, "ambiguity": ambiguity or {},
            "v1": {"n_violations": violations, "n_cross_pool_group_overlaps": 0}}


def _allv(seed, measurable=(7,), eligible=(), budget=25, counts=None):
    return _rec("REAL_ONLY_ALL_LABELS", seed,
                [_step(13, region=eligible, measurable=measurable, eligible=list(eligible),
                       counts=counts)], budget)


def _world(budget=25, *, go=3, assess=3, hit_seeds=3, v2_empty=5, violations=0,
           frozen_misses_drift=False, allv_measurable=(7,), allv_residual=(), allv_repair_seeds=5,
           ro_eligible=(7,), ambiguity=None):
    """5 seeds x (FROZEN, REAL_ONLY, REAL_ONLY_ALL_LABELS). `hit_seeds` seeds have `assess`
    assessable and `go` GO windows (go <= assess) at budget `budget`."""
    recs = []
    for s in range(5):
        hit = s < hit_seeds
        frozen = [_step(3, region=() if s < v2_empty else (0,)), _step(4)]
        ro = []
        for i in range(9):
            ass = hit and i < assess
            frozen.append(_step(5 + i, measurable=(7,) if ass else (),
                                region=(7,) if ass and not frozen_misses_drift else ()))
            ro.append(_step(5 + i, measurable=(7,) if ass else (),
                            eligible=list(ro_eligible) if hit and i < go else []))
        recs += [_rec("FROZEN", s, frozen, budget, violations=violations),
                 _rec("REAL_ONLY", s, ro, budget, ambiguity=ambiguity)]
        # seeds below `allv_repair_seeds` repair every class; the others keep `allv_residual`
        recs.append(_allv(s, allv_measurable, allv_residual if s >= allv_repair_seeds else (),
                          budget))
    return recs


def _eval(records_by_budget, prereg=True, problems=(), nesting=()):
    return evaluate_p0(records_by_budget, AUDITS, CRIT, prereg, problems, n_min=N_MIN,
                       eps_def=EPS_DEF, nesting_audits=nesting)


# ---------------------------------------------------- per-budget status (E1, data adequacy)
def test_unmeasurable_cannot_override_a_reachable_go():
    """The old rule vetoed GO when >80% of pooled cells were unmeasurable. Here 3 seeds have 3 GO
    windows each (9 of 45 cells = 80% unassessable): GO must still win."""
    out = _eval({25: _world(25, go=3, assess=3), 100: _world(100, go=0, assess=0)})
    st = out["data_adequacy"]["per_budget"][25]
    assert st["status"] == "GO" and st["unmeasurable_cell_fraction_descriptive"] >= 0.8
    assert out["data_adequacy"]["statuses"] == {25: "GO", 100: "UNMEASURABLE"}
    assert out["validity"]["all_pass"] and out["h1"]["outcome"] == "GO"
    assert out["h1"]["scope"] == "GO at B=25; B=100 unmeasurable"


def test_reachable_but_not_reached_go_is_no_room_not_unmeasurable():
    out = _eval({25: _world(25, go=0, assess=3), 100: _world(100, go=1, assess=3)})
    assert out["data_adequacy"]["statuses"] == {25: "NO_ROOM", 100: "NO_ROOM"}
    assert out["h1"]["outcome"] == "NO_GO_NO_ROOM"


def test_data_inadequacy_is_unmeasurable_and_never_invalid():
    out = _eval({25: _world(25, go=0, assess=1), 100: _world(100, go=0, assess=0)})
    assert out["data_adequacy"]["statuses"] == {25: "UNMEASURABLE", 100: "UNMEASURABLE"}
    assert out["validity"]["all_pass"] and out["validity"]["failed_checks"] == []
    assert out["data_adequacy"]["insufficient_support_is_never_invalid"] is True
    assert out["h1"]["outcome"] == "INCONCLUSIVE_UNMEASURABLE"
    # support is also UNMEASURABLE when only 2 seeds have enough windows, or 1 window each
    assert budget_status(_world(25, go=0, assess=3, hit_seeds=2), [7], CRIT, N_MIN)["status"] == \
        "UNMEASURABLE"
    assert budget_status(_world(25, go=0, assess=1, hit_seeds=5), [7], CRIT, N_MIN)["status"] == \
        "UNMEASURABLE"


def test_status_boundaries_are_the_preregistered_counts():
    f = lambda **k: budget_status(_world(25, **k), [7], CRIT, N_MIN)["status"]  # noqa: E731
    assert f(go=2, assess=2, hit_seeds=3) == "GO"
    assert f(go=1, assess=2, hit_seeds=3) == "NO_ROOM"
    assert f(go=2, assess=2, hit_seeds=2) == "UNMEASURABLE"
    assert f(go=0, assess=2, hit_seeds=3) == "NO_ROOM"
    assert f(go=0, assess=1, hit_seeds=5) == "UNMEASURABLE"


def test_t_d_never_counts_toward_cells_or_integrity():
    """t_d only sees pre-drift labels. One real window plus a t_d cell would reach the 2-window
    bar if t_d counted; it must not."""
    recs = _world(25, go=1, assess=1)
    for r in recs:
        if r["condition"] == "REAL_ONLY":
            r["steps"].insert(0, _step(4, region=(7,), measurable=(7,), eligible=[7]))
        if r["condition"] == "FROZEN":
            r["steps"].insert(2, _step(4, region=(), measurable=(7,)))   # measurable but not in A
    assert budget_status(recs, [7], CRIT, N_MIN)["status"] == "UNMEASURABLE"
    assert budget_status(recs, [7], CRIT, N_MIN)["per_seed"][0]["n_go"] == 1   # only t=5 counts
    assert evaluate_p0({25: recs, 100: _world(100)}, AUDITS, CRIT, True, n_min=N_MIN,
                       eps_def=EPS_DEF)["validity"]["v3_integrity"]["pass"]


def test_statuses_partition_over_random_per_seed_support():
    rng = np.random.default_rng(0)
    for _ in range(300):
        recs = []
        for s in range(5):
            assess = int(rng.integers(0, 10))
            go = int(rng.integers(0, assess + 1))
            ro = [_step(5 + i, measurable=(7,) if i < assess else (),
                        eligible=[7] if i < go else []) for i in range(9)]
            recs.append(_rec("REAL_ONLY", s, ro))
        out = budget_status(recs, [7], CRIT, N_MIN)
        n_go = sum(v["n_go"] >= 2 for v in out["per_seed"].values())
        n_ad = sum(v["n_assessable"] >= 2 for v in out["per_seed"].values())
        expected = "GO" if n_go >= 3 else "NO_ROOM" if n_ad >= 3 else "UNMEASURABLE"
        assert out["status"] == expected and out["status"] in STATUSES
        assert not out["inconsistent_go_cells"]          # a GO cell is always an assessable cell
        if out["status"] == "GO":
            assert n_ad >= 3                              # GO implies assessable


# ------------------------------------------------------------------------ V3 integrity
def test_v3_integrity_violation_invalidates_the_run():
    out = _eval({25: _world(25, frozen_misses_drift=True), 100: _world(100)})
    v3 = out["validity"]["v3_integrity"]
    assert not v3["pass"] and v3["violations"] and v3["violations"][0]["class"] == 7
    assert out["validity"]["failed_checks"] == ["v3_integrity"]
    assert out["h1"]["outcome"] == "INVALID" and out["h1"]["failed_checks"] == ["v3_integrity"]


def test_v3_is_vacuous_not_failed_when_nothing_is_measurable():
    out = _eval({25: _world(25, go=0, assess=0), 100: _world(100, go=0, assess=0)})
    v3 = out["validity"]["v3_integrity"]
    assert v3["pass"] and v3["n_cells_checked"] == 0 and v3["violations"] == []


def test_go_cell_without_support_is_an_integrity_violation():
    recs = _world(25, go=3, assess=3)
    for r in recs:
        if r["condition"] == "REAL_ONLY" and r["seed"] == 0:
            r["steps"][0]["measurable"] = []           # GO cell that is not assessable
    out = _eval({25: recs, 100: _world(100)})
    assert not out["validity"]["v3_integrity"]["pass"]
    assert out["validity"]["v3_integrity"]["go_cells_not_assessable"]


# ------------------------------------------------------------------------ V4 / repairable set
def test_repairable_set_is_classwise_from_the_positive_control():
    # class 7 repaired in seeds 0-2; class 8 repaired only in seeds 0-1; class 3 is not a drift class
    allv = []
    for s in range(5):
        meas = (7, 8, 3)
        resid = ([] if s < 3 else [7]) + ([] if s < 2 else [8]) + [3]
        allv.append(_allv(s, meas, resid))
    out = check_v4({25: allv}, CRIT, N_MIN)
    assert out["repairable_set"] == [7] and out["pass"] and out["budget_independent"]
    cls = out["per_budget"][25]["per_class_seed_counts"]
    assert cls[7]["repaired"] == 3 and cls[8]["repaired"] == 2 and 3 not in cls
    assert 8 in out["per_budget"][25]["unrepaired_classes"] and 7 not in \
        out["per_budget"][25]["unrepaired_classes"]
    assert cls[8]["residual_deficiency"] == 3


def test_unrepaired_causes_are_reported_separately():
    allv = []
    for s in range(5):
        counts = [10] * NK
        counts[8] = 2                                       # thin real support for class 8
        allv.append(_allv(s, measurable=(7, 8), eligible=(), counts=counts))
    out = check_v4({25: allv}, CRIT, N_MIN)
    assert out["repairable_set"] == [7]
    cls = out["per_budget"][25]["per_class_seed_counts"]
    assert cls[8] == {"repaired": 0, "residual_deficiency": 0, "thin_real_support": 5,
                      "unmeasurable": 0}
    allv = [_allv(s, measurable=(7,), eligible=()) for s in range(5)]
    assert check_v4({25: allv}, CRIT, N_MIN)["per_budget"][25]["per_class_seed_counts"][8][
        "unmeasurable"] == 5


def test_v4_fails_when_abundant_labels_repair_no_drift_class():
    out = _eval({25: _world(25, allv_residual=(7,), allv_repair_seeds=0),
                 100: _world(100, allv_residual=(7,), allv_repair_seeds=0)})
    assert not out["validity"]["v4_repairability"]["pass"]
    assert out["validity"]["v4_repairability"]["repairable_set"] == []
    assert out["h1"]["outcome"] == "INVALID" and out["h1"]["failed_checks"] == ["v4_repairability"]


def test_a_residual_pre_drift_class_in_the_control_neither_invalidates_nor_counts():
    # the control still has deficient PRE-drift class 3, but drift class 7 is repaired
    allv = [_allv(s, measurable=(7, 3), eligible=(3,)) for s in range(5)]
    assert check_v4({25: allv, 100: [dict(r, budget=100) for r in allv]}, CRIT, N_MIN)["pass"]


def test_repairable_set_must_be_identical_at_every_budget():
    a = [_allv(s, measurable=(7, 8), eligible=(8,)) for s in range(5)]          # R = {7}
    b = [_allv(s, measurable=(7, 8), eligible=(7,), budget=100) for s in range(5)]   # R = {8}
    out = check_v4({25: a, 100: b}, CRIT, N_MIN)
    assert not out["budget_independent"] and not out["pass"] and out["repairable_set"] == []


def test_go_counts_only_repairable_classes():
    # class 8 looks deficient (in I) in every window but is not repairable -> never a GO
    recs = _world(25, go=3, assess=3, ro_eligible=(8,), allv_measurable=(7, 8),
                  allv_residual=(8,))
    st = budget_status(recs, [7], CRIT, N_MIN)
    assert st["status"] == "NO_ROOM" and st["per_seed"][0]["n_go"] == 0
    # a repairable class alongside it does count, a non-drift class does not
    recs = _world(25, go=3, assess=3, ro_eligible=(7, 8))
    assert budget_status(recs, [7], CRIT, N_MIN)["status"] == "GO"
    recs = _world(25, go=3, assess=3, ro_eligible=(3,))
    assert budget_status(recs, [7], CRIT, N_MIN)["status"] == "NO_ROOM"


def test_assessable_requires_a_repairable_measurable_class_with_real_support():
    thin_counts = [10] * 8 + [2] + [10]          # class 7 has 10 real rows, class 8 only 2
    recs = _world(25, go=0, assess=3)
    for r in recs:
        for s in r["steps"]:
            s["real_class_counts"] = list(thin_counts)
    assert budget_status(recs, [7], CRIT, N_MIN)["status"] == "NO_ROOM"       # 7 measurable, supported
    assert budget_status(recs, [8], CRIT, N_MIN)["status"] == "UNMEASURABLE"  # 8 never measurable
    assert budget_status(recs, [], CRIT, N_MIN)["status"] == "UNMEASURABLE"   # nothing repairable
    for r in recs:                                                            # now 8 is measurable
        for s in r["steps"]:
            s["measurable"] = [8] if s["measurable"] else []
    assert budget_status(recs, [8], CRIT, N_MIN)["status"] == "UNMEASURABLE"  # ... but thin (2 < 5)
    assert budget_status(recs, [7], CRIT, N_MIN)["status"] == "UNMEASURABLE"  # 7 not measurable now


# ------------------------------------------------------------------------ V2 diagnostic
def test_v2_failure_does_not_block_p0_but_blocks_p1():
    out = _eval({25: _world(25, v2_empty=2), 100: _world(100, v2_empty=2)})
    v2 = out["diagnostics"]["v2_null_region"]
    assert not v2["pass"] and v2["p1_blocked"] and v2["gates_p0_outcome"] is False
    assert out["validity"]["all_pass"] and "v2_null_region" not in out["validity"]
    assert out["h1"]["outcome"] == "GO"
    ok = _eval({25: _world(25), 100: _world(100)})
    assert ok["diagnostics"]["v2_null_region"]["pass"] and not \
        ok["diagnostics"]["v2_null_region"]["p1_blocked"]


def test_v2_thresholds_are_four_of_five_seeds_empty_at_the_last_pre_drift_window():
    def frozen(n_empty):
        return [_rec("FROZEN", s, [_step(3, region=() if s < n_empty else (0,))])
                for s in range(5)]
    assert check_v2(frozen(5), CRIT)["pass"] and check_v2(frozen(4), CRIT)["pass"]
    out = check_v2(frozen(3), CRIT)
    assert not out["pass"] and out["n_seeds_region_empty"] == 3 and out["required"] == 4
    recs = [_rec("FROZEN", s, [_step(2, region=(0,)), _step(3, region=())]) for s in range(5)]
    assert check_v2(recs, CRIT)["pass"]                       # only the LAST pre-drift window
    assert not check_v2([_rec("FROZEN", s, [_step(2)]) for s in range(5)], CRIT)["pass"]


# ------------------------------------------------------------ outcome state machine (E7)
def test_outcome_table_over_every_status_combination():
    for statuses in itertools.chain(itertools.product(STATUSES, repeat=2),
                                    itertools.product(STATUSES, repeat=3)):
        grid = dict(zip((25, 100, 400), statuses))
        expected = ("GO" if "GO" in statuses else "NO_GO_NO_ROOM" if "NO_ROOM" in statuses
                    else "INCONCLUSIVE_UNMEASURABLE")
        assert decide_outcome(True, grid) == expected
        assert decide_outcome(False, grid) == "INVALID"       # invalid beats every status
        assert decide_outcome(True, grid) in OUTCOMES


def test_inconclusive_mixed_is_removed():
    assert OUTCOMES == ("INVALID", "GO", "NO_GO_NO_ROOM", "INCONCLUSIVE_UNMEASURABLE")
    assert not hasattr(validity, "mostly_unmeasurable")
    assert "INCONCLUSIVE_MIXED" not in Path(validity.__file__).read_text().replace(
        "INCONCLUSIVE_MIXED is removed", "")
    assert "INCONCLUSIVE_MIXED" not in spec_rules_text()


def test_nested_budgets_unmeasurable_then_no_room_is_no_go_with_explicit_scope():
    """B=25 unmeasurable, B=100 no room -> NO_GO_NO_ROOM at the evaluable budget, stated plainly."""
    out = _eval({25: _world(25, go=0, assess=1), 100: _world(100, go=0, assess=3)})
    assert out["data_adequacy"]["statuses"] == {25: "UNMEASURABLE", 100: "NO_ROOM"}
    assert out["h1"]["outcome"] == "NO_GO_NO_ROOM"
    assert out["h1"]["scope"] == "NO_ROOM at B=100; B=25 unmeasurable"
    assert scope_statement({25: "GO", 100: "NO_ROOM", 400: "UNMEASURABLE"}) == \
        "GO at B=25; NO_ROOM at B=100; B=400 unmeasurable"


def test_outcome_is_assigned_only_for_the_preregistered_configuration():
    worlds = {25: _world(25), 100: _world(100)}
    out = _eval(worlds, prereg=False, problems=["only a smoke run"])
    assert out["h1"]["status"] == "withheld_not_preregistered" and out["h1"]["outcome"] is None
    assert out["h1"]["problems"] == ["only a smoke run"]
    assert out["validity"]["all_pass"] and out["data_adequacy"]["statuses"][25] == "GO"
    ok = _eval(worlds)
    assert ok["h1"]["status"] == "evaluated" and ok["h1"]["outcome"] == "GO"
    bad = _eval({25: _world(25, violations=1), 100: _world(100)})
    assert bad["h1"]["outcome"] == "INVALID" and bad["h1"]["failed_checks"] == ["v1_leakage_audit"]


def test_blocks_are_separate_and_ordered_validity_diagnostics_adequacy_outcome():
    out = _eval({25: _world(25), 100: _world(100)})
    assert list(out) == ["validity", "diagnostics", "data_adequacy", "h1"]
    assert set(out["validity"]) == {"v1_leakage_audit", "v3_integrity", "v4_repairability",
                                    "all_pass", "failed_checks"}
    assert set(out["diagnostics"]) == {"v2_null_region", "label_ambiguity",
                                       "cross_pool_contamination"}


# ------------------------------------------- cross-pool / contradictory-label reporting (E5)
def test_cross_pool_duplicates_are_reported_without_invalidating(run):
    result, _ = run
    s = result["summary"]
    assert s["validity"]["v1_leakage_audit"]["pass"]
    assert s["validity"]["v1_leakage_audit"]["n_cross_pool_group_overlaps_informational"] > 0
    assert s["data"]["label_conflicts_diagnostic_only"]["n_groups_in_both_pools"] > 0
    cont = s["diagnostics"]["cross_pool_contamination"]
    assert set(cont) == set(BUDGETS)
    node = cont[100]["REAL_ONLY"]["real"]
    assert set(node) == {"S_report", "S_gate", "S_sel", "S_cal", "D_ref"}
    assert all(set(v) == {"drift_pool_total", "pre_pool_total", "drift_pool_max_seed"}
               for v in node.values())
    assert all(v["pre_pool_total"] == 0 for v in node.values())    # same-pool overlap is impossible


def test_contradictory_labels_are_flagged_on_a_go_class_but_never_gate():
    amb = {"d_sel": {7: {"share": 0.20}}, "e_pooled": {7: {"share": 0.0}}}
    flagged = _eval({25: _world(25, ambiguity=amb), 100: _world(100, ambiguity=amb)})
    row = flagged["diagnostics"]["label_ambiguity"]["go_classes"][7]
    assert row["possibly_ambiguity_driven"] and row["max_d_sel_share"] == 0.20
    assert row["seeds_with_go_cell"] > 0
    clean = {"d_sel": {7: {"share": 0.04}}, "e_pooled": {7: {"share": 0.01}}}
    unflagged = _eval({25: _world(25, ambiguity=clean), 100: _world(100, ambiguity=clean)})
    assert not unflagged["diagnostics"]["label_ambiguity"]["go_classes"][7][
        "possibly_ambiguity_driven"]
    assert flagged["h1"]["outcome"] == unflagged["h1"]["outcome"] == "GO"       # never gates
    assert flagged["validity"]["all_pass"]
    assert "intrinsically" in flagged["diagnostics"]["label_ambiguity"]["interpretation"] or \
        "unrepairable" in flagged["diagnostics"]["label_ambiguity"]["interpretation"]


def test_contradictory_vectors_in_a_run_are_counted_in_the_header_and_records(data, tmp_path):
    """Plant Friday rows that copy Monday feature vectors but carry a drift label: the same vector
    is then benign-ish on Monday and a drift class on Friday."""
    y = data.y.copy()
    mon = np.isin(data.group, data.group[data.day == "Monday"]) & (data.day == "Friday")
    y[mon] = 4
    planted = DataBundle(X=data.X, y=y, day=data.day, group=data.group,
                         class_names=data.class_names, feature_names=data.feature_names)
    res = p0.run_p0(planted, budgets=(100,), seeds=(0,), params=PARAMS, scenario_cfg=CFG)
    conf = res["summary"]["data"]["label_conflicts_diagnostic_only"]
    assert conf["n_groups_with_different_labels_across_pools"] > 0
    assert conf["n_groups_with_conflicting_labels_corpus"] >= \
        conf["n_groups_with_different_labels_across_pools"]
    run0 = res["budget_files"][100]["runs"][0]
    assert set(run0["ambiguity"]) == {"d_sel", "e_pooled"}
    assert run0["ambiguity"]["e_pooled"][4]["n_rows"] > 0
    assert res["summary"]["validity"]["v1_leakage_audit"]["pass"]       # still legal for V1


# ------------------------------------------------------ spec / criteria / provenance (E8)
def test_p0_criteria_are_pinned_to_the_approved_plan():
    c = P0Criteria()
    assert (c.scenario, c.budgets, c.seeds) == ("S1", (25, 100), (0, 1, 2, 3, 4))
    assert (c.v2_min_seeds_empty, c.repairable_min_seeds) == (4, 3)
    assert (c.adequate_min_windows, c.adequate_min_seeds) == (2, 3)
    assert (c.go_min_windows, c.go_min_seeds) == (2, 3)


def test_the_spec_section_states_the_same_constants_as_the_code():
    text = " ".join(spec_rules_text().split())      # robust to line wrapping
    for phrase in ("at least 3 of 5 seeds have at least 2 GO cells",
                   "at least 3 of 5 seeds have at least 2 assessable cells",
                   "repaired in at least 3 of 5 seeds", "at least 4 of 5 seeds",
                   "t > t_d", "NO_GO_NO_ROOM", "INCONCLUSIVE_UNMEASURABLE", "INVALID",
                   "NO_ROOM at B=100; B=25 unmeasurable", "never gate it", "intrinsically",
                   "does NOT fail V1"):
        assert phrase in text, phrase
    assert "v1.2" in SPEC_PATH.read_text().split("<!-- P0-DECISION-RULES:BEGIN -->")[0]


def test_criteria_digest_changes_with_every_constant_and_with_the_version(monkeypatch):
    base = P0Criteria().digest()
    assert len(base) == 64 and P0Criteria().digest() == base
    for field, value in (("go_min_seeds", 2), ("go_min_windows", 3), ("adequate_min_seeds", 2),
                         ("adequate_min_windows", 3), ("repairable_min_seeds", 2),
                         ("v2_min_seeds_empty", 3), ("budgets", (25, 100, 400))):
        assert replace(P0Criteria(), **{field: value}).digest() != base, field
    monkeypatch.setattr(validity, "SPEC_VERSION", "9.9")
    assert P0Criteria().digest() != base


def test_spec_rules_hash_tracks_the_frozen_text(tmp_path):
    h = spec_rules_sha256()
    assert len(h) == 64 and spec_rules_sha256() == h
    edited = tmp_path / "spec.md"
    edited.write_text(SPEC_PATH.read_text().replace("at least 3 of 5 seeds have at least 2 GO cells",
                                                    "at least 2 of 5 seeds have at least 2 GO cells"))
    assert spec_rules_sha256(edited) != h
    outside = tmp_path / "outside.md"
    outside.write_text(SPEC_PATH.read_text().replace("# Proteus", "# Proteus (edited title)"))
    assert spec_rules_sha256(outside) == h                       # text outside the section is free
    empty = tmp_path / "none.md"
    empty.write_text("no rules here")
    with pytest.raises(RuntimeError):
        spec_rules_sha256(empty)


# ------------------------------------------------ v1.3: the amendment must not touch P0 itself
V12_RULES_SHA256 = "779e679aa006afafc1caa79acdc4c3b659ec151a241b81e7dd4224011aabb11e"


def test_p0_decision_rules_are_byte_identical_to_v1_2():
    """v1.3 relabelled envelope rejections only. The frozen P0 decision procedure (spec L.1) must
    hash exactly as it did in v1.2; a deliberate rules change has to update this pin."""
    assert spec_rules_sha256() == V12_RULES_SHA256
    assert SPEC_VERSION == "1.3"
    assert P0Criteria().digest() != ""            # constants pinned separately above


def test_p0_outcome_does_not_depend_on_the_envelope_rejection_labels():
    """Rejection reasons are descriptive. Swapping every reason between the old over-called label
    and the v1.3 label must leave validity, diagnostics, adequacy and the outcome untouched."""
    import copy
    base = {25: _world(25, go=0, assess=3), 100: _world(100, go=3, assess=3)}
    alt = copy.deepcopy(base)
    for recs in alt.values():
        for r in recs:
            for s in r["steps"]:
                s["reason"] = "envelope_inconclusive"
    for recs in base.values():
        for r in recs:
            for s in r["steps"]:
                s["reason"] = "envelope_violated"
    a, b = _eval(base), _eval(alt)
    assert a == b
    assert a["h1"]["outcome"] == "GO"


# --------------------------------------------------------- runner contract / provenance
def test_result_files_exist_are_strict_json_and_order_the_blocks(run):
    _, out = run
    files = sorted(p.name for p in out.glob("*.json"))
    assert files == ["intervention_p0_T_B100.json", "intervention_p0_T_B30.json",
                     "intervention_p0_T_summary.json"]
    for name in files:
        doc = loads_strict((out / name).read_text())               # raises on bare NaN / Infinity
        keys = list(doc)
        assert keys.index("validity") < keys.index("diagnostics") < keys.index("data_adequacy") \
            < keys.index("h1")
        assert set(doc["validity"]) >= {"v1_leakage_audit", "v3_integrity", "v4_repairability"}
        assert "v2_null_region" in doc["diagnostics"] and "v2_null_region" not in doc["validity"]


def test_every_result_carries_the_required_provenance(run, data):
    result, out = run
    doc = loads_strict((out / "intervention_p0_T_B100.json").read_text())
    assert doc["spec_version"] == SPEC_VERSION == "1.3"
    assert doc["params_digest"] == PARAMS.digest() and len(doc["params_digest"]) == 64
    assert doc["criteria_digest"] == P0Criteria().digest()
    assert doc["spec_rules_sha256"] == spec_rules_sha256()
    assert doc["git_sha"] is None or len(doc["git_sha"]) == 40
    assert "git_dirty" in doc and doc["budget"] == 100 and doc["seeds"] == list(SEEDS)
    assert doc["preregistered_configuration"] is False and doc["preregistration_problems"]
    assert doc["h1"]["status"] == "withheld_not_preregistered" and doc["h1"]["outcome"] is None
    assert doc["data_adequacy"]["this_budget_status"] in STATUSES
    assert doc["criteria"]["go_min_seeds"] == 3 and doc["params"]["alpha"] == 0.05

    for seed in SEEDS:
        m = doc["manifests"][str(seed)]
        expected = build_partitions(data, replace(CFG, budget=100), seed)
        assert m["digest"] == expected.digest() and m["data_fingerprint"]
        runs = [r for r in doc["runs"] if r["seed"] == seed]
        assert [r["condition"] for r in runs] == list(p0.CONDITION_NAMES)
        assert {r["manifest_digest"] for r in runs} == {m["digest"]}     # one manifest, 3 conditions
        digests = {r["condition"]: r["label_stream_digest"] for r in runs}
        assert digests["FROZEN"] == digests["REAL_ONLY"] != digests["REAL_ONLY_ALL_LABELS"]
        for r in runs:
            assert r["seed"] == seed and r["budget"] == 100 and r["scenario"] == "T"
            assert r["timings"]["total_s"] > 0 and r["timings"]["base_fit_s"] > 0
            assert len(r["steps"]) == CFG.n_pre_windows + CFG.n_post_windows
            assert all({"timings", "v1_audit", "real_class_counts"} <= set(s) for s in r["steps"])
            assert set(r["summary"]["recovery"]["region"]) <= {4, 5}
            assert set(r["ambiguity"]) == {"d_sel", "e_pooled"} and r["contamination"]


def test_run_records_expose_taxonomy_support_and_effects(run):
    result, _ = run
    for r in result["budget_files"][100]["runs"]:
        s = r["summary"]
        if r["condition"] == "FROZEN":
            assert s["reason_counts"] == {} and s["n_promotions"] == 0
            assert all(st["reason"] == "frozen" and not st["promoted"]
                       for st in r["steps"] if st["controller_active"])
            assert all(st["deployed_is_base"] for st in r["steps"])
        else:
            assert set(s["reason_counts"]) <= set(REASONS)
            assert sum(s["reason_counts"].values()) == CFG.n_post_windows
            for st in r["steps"]:
                if st["controller_active"] and st["decision"] and st["decision"]["report"]:
                    assert {"n_gate_rows", "gate_support", "n_s_gate_benign"} <= \
                        set(st["decision"]["report"])
        eff = s["stable_reference_effect"]
        assert set(eff["base"]) >= {"stable_macro_f1", "benign_fpr"}
        assert "final_stable_macro_f1_drop" in eff and "worst_benign_fpr_increase" in eff
        assert "measurable_windows_by_class" in s and "support_counts_per_decision" in s
    agg = result["budget_files"][100]["aggregate"]
    assert set(agg["recovery_auc"]) == set(p0.CONDITION_NAMES)
    assert "paired_descriptive_not_an_h1_test" in agg


def test_replay_is_deterministic_under_the_same_seed_and_configuration(data):
    def decisions():
        res = p0.run_p0(data, budgets=(100,), seeds=(0,), params=PARAMS, scenario_cfg=CFG)
        out = []
        for r in res["budget_files"][100]["runs"]:
            out.append((r["condition"], r["manifest_digest"], r["label_stream_digest"],
                        [(s["t"], s["reason"], s["promoted"], tuple(s["region"]),
                          tuple(s["measurable"]), s["eligible"] and tuple(s["eligible"]),
                          s["e_conf_cells"]) for s in r["steps"]]))
        return out
    assert decisions() == decisions()


def test_an_outcome_is_assigned_end_to_end_on_separable_data(data, monkeypatch):
    """Whole pipeline (replay -> records -> validity -> adequacy -> outcome) on data where the
    classes are well separated, with the preregistration check bypassed for the fixture."""
    X = data.X + 5.0 * data.y[:, None].astype(np.float32)
    sep = DataBundle(X=X, y=data.y, day=data.day, group=hash_rows(X),
                     class_names=data.class_names, feature_names=data.feature_names)
    monkeypatch.setattr(p0, "check_preregistered", lambda *a, **k: (True, []))
    res = p0.run_p0(sep, budgets=BUDGETS, seeds=SEEDS, params=PARAMS, scenario_cfg=CFG)
    h1 = res["summary"]["h1"]
    assert h1["status"] == "evaluated" and h1["outcome"] in OUTCOMES
    assert set(h1["budget_statuses"]) == set(BUDGETS) and h1["scope"]
    assert all(s in STATUSES for s in h1["budget_statuses"].values())
    if h1["outcome"] == "INVALID":
        assert h1["failed_checks"]


# ---------------------------------------------------------------- information boundaries
class _Spy:
    name = "SPY"
    label_regime = LABEL_REGIME_BUDGET

    def __init__(self):
        self.seen = []

    def decide(self, view, incumbent, ctx):
        self.seen.append((type(view), type(ctx), view.ref_X.flags.writeable,
                          view.real_X.flags.writeable, ctx.anchor is not None))
        return Outcome(incumbent, False, "frozen", None, (), None, {})


def test_conditions_receive_only_a_read_only_view_and_a_context(data, manifest):
    spy = _Spy()
    state = p0.TrackedState(data, manifest)
    state.ingest(next(iter(StreamReplay(manifest))))
    base = CandidateBuilder(PARAMS, 0).build_base(state.view())
    rec = p0.run_condition(data, manifest, spy, PARAMS, base,
                           {"stable_macro_f1": 0.0, "benign_fpr": 0.0}, p0.Auditor(data, manifest),
                           [4, 5])
    assert len(spy.seen) == CFG.n_post_windows
    assert all(v is ControllerView and c is DecisionContext and not ro and not rw and anchor
               for v, c, ro, rw, anchor in spy.seen)
    assert rec["v1"]["n_violations"] == 0


def test_runner_never_hands_the_dataset_or_manifest_to_decide():
    """Static check: every `.decide(...)` call in p0.py passes exactly (view, incumbent, ctx)."""
    tree = ast.parse(Path(p0.__file__).read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "decide"]
    assert calls
    for c in calls:
        assert [a.id for a in c.args] == ["view", "incumbent", "ctx"] and not c.keywords
