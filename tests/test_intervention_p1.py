"""P1 runner and arms (SPEC v1.4): equivalence with the frozen P0 REAL_ONLY, canary, shadow scoring,
isolation, determinism, provenance and the preregistration pins. Synthetic data, 15-tree forests."""
import ast
import inspect
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import proteus.intervention.arms as arms_mod
import proteus.intervention.controller as ctl
import proteus.intervention.p0 as p0
import proteus.intervention.p1 as p1
from proteus.intervention.arms import (
    ARM_NAMES, ArmOutcome, ControllerArm, FixedDoseArm, RealOnlyArm, make_arms)
from proteus.intervention.conditions import DecisionContext, RealOnly
from proteus.intervention.controller import DataOperator
from proteus.intervention.diagnostics import ambiguous_groups
from proteus.intervention.learner import CandidateBuilder, ResidualSets
from proteus.intervention.p1_spec import (
    ALL_ARMS, P1_SPEC_VERSION, P1Criteria, rules_sha256, rules_text)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import ScenarioConfig, SPEC_VERSION, StreamReplay, build_partitions
from proteus.intervention.serialize import loads_strict
from proteus.intervention.validity import spec_rules_sha256
from tests.test_intervention_learner import make_learnable_view
from tests.test_intervention_protocol import _make_data

CFG = ScenarioConfig("T", ("Monday", "Tuesday", "Wednesday", "Thursday"), ("Friday",),
                     window_size=600, n_pre_windows=2, n_post_windows=5, budget=100,
                     s_size=400, ref_size=500, real_buffer_cap=400, eval_buffer_cap=400)
PARAMS = InterventionParams(benign_label="c0", rf_n_estimators=15, n_boot=200)   # speed only
CRIT = replace(P1Criteria(), seeds=(0, 1))


@pytest.fixture(scope="module")
def data():
    return _make_data()


@pytest.fixture(scope="module")
def run(data, tmp_path_factory):
    out = tmp_path_factory.mktemp("p1_out")
    amb = ambiguous_groups(data.group, data.y)
    path = p1.run_seed(data, 0, ALL_ARMS, CRIT, PARAMS, CFG, [4, 5], out, amb,
                       progress=lambda m: None)
    return loads_strict(path.read_text()), path


def arm_run(doc, name):
    return next(r for r in doc["runs"] if r["arm"] == name)


# ------------------------------------------------------------------------------ provenance
def test_result_file_is_strict_json_with_the_required_provenance(run):
    doc, path = run
    assert doc["kind"] == "p1_seed_result" and path.name == "intervention_p1_T_B100_seed0.json"
    assert doc["p1_spec_version"] == P1_SPEC_VERSION == "1.4"
    assert doc["partition_spec_version"] == SPEC_VERSION == "1.3"
    assert doc["p1_rules_sha256"] == rules_sha256() and doc["params_digest"] == PARAMS.digest()
    assert doc["p1_criteria_digest"] == CRIT.digest()
    assert doc["repairable_set_R"] == [4, 5] and "git_sha" in doc and "versions" in doc
    assert [r["arm"] for r in doc["runs"]] == list(ALL_ARMS)
    assert doc["preregistered_configuration"] is False        # synthetic scenario, not S1
    assert doc["manifest"]["matches_p0_manifest"] is None
    assert doc["manifest"]["digest"] == arm_run(doc, "REAL_ONLY")["manifest_digest"]


def test_every_arm_passes_the_v1_leakage_audit(run):
    doc, _ = run
    for r in doc["runs"]:
        assert r["v1"].get("n_violations", 0) == 0, r["arm"]
        assert r["v1"].get("n_unlabelled_rows", 0) == 0 and r["v1"].get("n_future_rows", 0) == 0


def test_arm_registry_matches_the_preregistered_list():
    assert ARM_NAMES == ALL_ARMS and len(set(ALL_ARMS)) == 23
    assert len(make_arms()) == 23
    assert [a.name for a in make_arms(["REAL_ONLY", "CTRL-SMOTE"])] == ["REAL_ONLY", "CTRL-SMOTE"]
    with pytest.raises(KeyError):
        make_arms(["nope"])


# ------------------------------------------------------------------------------ P0 equivalence
def test_real_only_without_canary_reproduces_the_frozen_p0_condition_step_for_step(data, run):
    doc, _ = run
    manifest = build_partitions(data, replace(CFG, budget=100), 0)
    aud = p0.Auditor(data, manifest, ambiguous_groups(data.group, data.y))
    st = p0.TrackedState(data, manifest)
    st.ingest(next(iter(StreamReplay(manifest))))
    base = CandidateBuilder(PARAMS, 0).build_base(st.view())
    k = len(data.class_names)
    benign = list(data.class_names).index("c0")
    stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
    bs = p0.s_report_stats(base, data, manifest, stable, benign, k, PARAMS.s_min)
    ref = p0.run_condition(data, manifest, RealOnly(), PARAMS, base, bs, aud,
                           p0.drift_classes_of(data, CFG))
    mine = arm_run(doc, "ABL-NO-CANARY-REAL")
    assert len(ref["steps"]) == len(mine["steps"])
    for a, b in zip(ref["steps"], mine["steps"]):
        assert (a["t"], a["reason"], a["promoted"], a["region"]) == (
            b["t"], b["reason"], b["promoted"], b["region"])
        assert a["e_conf_cells"] == b["e_conf_cells"] and a["eligible"] == b["eligible"]
    assert mine["counts"].get("rollbacks", 0) == 0


def test_controller_with_empty_need_set_decides_exactly_like_real_only(monkeypatch):
    view = make_learnable_view()
    p = replace(PARAMS, benign_label="benign")
    base = CandidateBuilder(p, 0).build_base(view)
    ctx = DecisionContext(t=3, seed=0, params=p, anchor=base)
    monkeypatch.setattr(ctl, "compute_residual_sets", lambda *a, **k: ResidualSets((), ()))
    ro = RealOnlyArm().decide(view, base, ctx)
    ca = ControllerArm("C", lambda: DataOperator("SMOTE", arms_mod.gen_smote)).decide(view, base, ctx)
    assert (ro.reason, ro.promoted, ro.region) == (ca.reason, ca.promoted, ca.region)
    probe = np.random.default_rng(5).normal(size=(200, 4)).astype(np.float32) * 5
    assert np.array_equal(ro.model.predict(probe), ca.model.predict(probe))
    assert ca.k == 0 and ca.stop_reason == "real_only_sufficient" and ca.branch == ro.branch


# ------------------------------------------------------------------------------ shadow scoring
def test_shadow_candidates_are_scored_on_the_next_window_after_the_decision(run):
    doc, _ = run
    steps = arm_run(doc, "ABL-NO-CANARY-REAL")["steps"]
    n_checked = 0
    for prev, cur in zip(steps, steps[1:]):
        if cur["phase"] != "post" or prev["phase"] != "post":
            continue
        has_candidate = prev["reason"] not in (None, "no_affected_region")
        assert ("theta_R" in cur["shadow"]) == bool(has_candidate)
        if has_candidate:
            sc = cur["shadow"]["theta_R"]
            assert sum(c for _, _, c in sc["cells"]) == cur["e_n"]
            assert sum(c for _, _, c in sc["cells_clean"] + sc["cells_ambig"]) == cur["e_n"]
            assert "s_report" in sc
            if prev["promoted"]:                         # promoted th_R == the next deployed model
                assert sc["cells"] == cur["e_conf_cells"]
            n_checked += 1
    assert n_checked >= 1


def test_oracle_reference_is_never_deployed_and_exposes_the_ladder(run):
    doc, _ = run
    r = arm_run(doc, "ORACLE_DOSE")
    assert r["counts"].get("promotions", 0) == 0 and r["is_reference"]
    assert all(s["deployed_is_base"] for s in r["steps"])
    shadows = {k for s in r["steps"] for k in s["shadow"]}
    assert shadows <= {"theta_R"} | {f"rho{x:g}" for x in PARAMS.rho_ladder[1:]}


def test_pre_drift_probe_records_a_noop_and_is_never_deployed(run):
    doc, _ = run
    steps = arm_run(doc, "CTRL-SMOTE")["steps"]
    probes = [s["probe"] for s in steps if s["phase"] == "pre" and s["t"] >= 1]
    assert probes and all(p is not None for p in probes)
    assert all(not p["promoted"] for p in probes)
    assert all(s["probe"] is None for s in steps if s["phase"] == "post" or s["t"] == 0)


# ------------------------------------------------------------------------------ canary
class _PromoteOnce:
    name, label_regime, canary, probe_pre_drift, is_reference = (
        "STUB", "budget", True, False, False)

    def __init__(self):
        self.done = False

    def decide(self, view, incumbent, ctx):
        if self.done:
            return ArmOutcome(incumbent, False, "incumbent", "stub_idle", "no_star", (1,), None,
                              None, None, 0, "stub", {})
        self.done = True
        model = CandidateBuilder(ctx.params, ctx.seed).build(view)
        return ArmOutcome(model, True, "real_only", "promoted", "no_star", (1,), (), model, None, 0,
                          "stub", {})


def test_a_rollback_restores_the_previous_model_exactly(data, monkeypatch):
    from proteus.intervention.gate14 import CanaryDecision
    manifest = build_partitions(data, replace(CFG, budget=100), 0)
    aud = p0.Auditor(data, manifest, ambiguous_groups(data.group, data.y))
    st = p0.TrackedState(data, manifest)
    st.ingest(next(iter(StreamReplay(manifest))))
    base = CandidateBuilder(PARAMS, 0).build_base(st.view())
    k = len(data.class_names)
    benign = list(data.class_names).index("c0")
    stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
    bs = p0.s_report_stats(base, data, manifest, stable, benign, k, PARAMS.s_min)
    seen = {}

    def fake_canary(new, prev, anchor, X, y, region, params, rng, **kw):
        seen["prev_is_base"] = prev is base
        seen["n_labels"] = len(y)
        return CanaryDecision(True, "utility_worse", {"n_rows": len(y)})

    monkeypatch.setattr(p1, "canary", fake_canary)
    rec = p1.run_arm(data, manifest, _PromoteOnce(), PARAMS, base, bs, aud,
                     p0.drift_classes_of(data, CFG), stable, benign)
    steps = rec["steps"]
    first = next(i for i, s in enumerate(steps) if s["promoted"])
    assert rec["counts"]["rollbacks"] == 1 and seen["prev_is_base"] and seen["n_labels"] > 0
    assert steps[first + 1]["canary"]["rollback"] is True
    assert steps[first + 1]["deployed_is_base"] and steps[first + 1]["s_report"] == bs
    frozen = p1.run_arm(data, manifest, make_arms(["FROZEN"])[0], PARAMS, base, bs, aud,
                        p0.drift_classes_of(data, CFG), stable, benign)
    for a, b in zip(steps[first + 2:], frozen["steps"][first + 2:]):
        assert a["e_conf_cells"] == b["e_conf_cells"]        # base model deployed again
    assert steps[first]["canary"] is None                     # nothing to check at promotion time


def test_the_canary_sees_only_labels_that_arrive_after_the_promotion(data, monkeypatch):
    from proteus.intervention.gate14 import CanaryDecision
    manifest = build_partitions(data, replace(CFG, budget=100), 0)
    aud = p0.Auditor(data, manifest, ambiguous_groups(data.group, data.y))
    st = p0.TrackedState(data, manifest)
    st.ingest(next(iter(StreamReplay(manifest))))
    base = CandidateBuilder(PARAMS, 0).build_base(st.view())
    k = len(data.class_names)
    stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
    bs = p0.s_report_stats(base, data, manifest, stable, 0, k, PARAMS.s_min)
    used = []

    def spy(new, prev, anchor, X, y, region, params, rng, **kw):
        used.append(X)
        return CanaryDecision(False, "keep", {})

    monkeypatch.setattr(p1, "canary", spy)
    p1.run_arm(data, manifest, _PromoteOnce(), PARAMS, base, bs, aud,
               p0.drift_classes_of(data, CFG), stable, 0)
    assert len(used) == 1
    forbidden = np.concatenate([w.e_idx for w in manifest.windows] + [manifest.s_report_idx,
                                                                      manifest.s_cal_idx])
    labelled = {tuple(r) for r in data.X[np.concatenate([w.l_idx for w in manifest.windows])]}
    forbidden_rows = {tuple(r) for r in data.X[forbidden]}
    for row in used[0]:
        assert tuple(row) in labelled and tuple(row) not in forbidden_rows - labelled


# ------------------------------------------------------------------------------ isolation
def test_no_arm_or_controller_module_can_reach_evaluation_data():
    for mod in (arms_mod, ctl):
        tree = ast.parse(Path(mod.__file__).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not {"e_idx", "u_idx", "s_report_idx", "s_cal_idx", "l_idx", "DataBundle",
                    "StreamReplay", "PartitionManifest"} & names, mod.__name__
        assert not {"proteus.intervention.cache", "proteus.intervention.p0",
                    "proteus.intervention.p1"} & imported, mod.__name__


def test_decide_has_no_handle_to_shadow_or_evaluation_state():
    for arm in make_arms():
        assert list(inspect.signature(arm.decide).parameters) == ["view", "incumbent", "ctx"]
    src = inspect.getsource(p1.run_arm)
    assert src.index("arm.decide(view, incumbent, ctx)") < src.index("pending_shadow = out.shadow")
    assert src.index("shadow_scores[name] = sc") < src.index("arm.decide(view, incumbent, ctx)")


# ------------------------------------------------------------------------------ determinism
def test_the_same_seed_gives_identical_decisions_and_scores(data, tmp_path):
    amb = ambiguous_groups(data.group, data.y)
    names = ["REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-4"]
    docs = []
    for i in range(2):
        path = p1.run_seed(data, 0, names, CRIT, PARAMS, CFG, [4, 5], tmp_path / str(i), amb,
                           progress=lambda m: None)
        docs.append(loads_strict(path.read_text()))

    def strip(d):
        for r in d["runs"]:
            r.pop("timings")
            for s in r["steps"]:
                s.pop("timings")
        for key in ("started_utc",):
            d.pop(key)
        return json.dumps(d, sort_keys=True)

    assert strip(docs[0]) == strip(docs[1])


# ------------------------------------------------------------------------------ preregistration pins
def test_p1_constants_are_pinned_to_the_preregistration_text():
    c = P1Criteria()
    assert (c.scenario, c.budget, c.seeds) == ("S1", 100, tuple(range(10)))
    assert (c.activity_min_seeds, c.fixed_rhos, c.sequence) == (6, (1.0, 4.0), ("H2", "H3a", "H3b", "H5"))
    assert (c.mmd_p_min, c.mmd_n_perm, c.degenerate_k0_share, c.rollback_share_max) == (
        0.05, 100, 0.8, 0.2)
    text = rules_text()
    for token in ("seeds 0–9", "B=100", "≥ 6 of 10", "{1,2,4,8,16}", "100 permutations", "p > 0.05",
                  "H2", "H3a", "H3b", "H5", "F10", "F11", "S2 P0", *ALL_ARMS):
        assert token in text, token
    assert arms_mod.N_PERM_MMD == c.mmd_n_perm and arms_mod.DONOR_ROWS == c.donor_rows
    assert ctl.WEIGHT_LADDER == c.thresh_ladder


def test_p0_rules_hash_is_untouched_by_the_v1_4_text_and_the_p1_hash_tracks_its_text(tmp_path):
    assert spec_rules_sha256() == "779e679aa006afafc1caa79acdc4c3b659ec151a241b81e7dd4224011aabb11e"
    spec = Path(p1.__file__).parents[2] / "docs" / "INTERVENTION_SPEC.md"
    edited = tmp_path / "spec.md"
    edited.write_text(spec.read_text().replace("seeds 0–9", "seeds 0–8"))
    assert rules_sha256(edited) != rules_sha256() and spec_rules_sha256(edited) == spec_rules_sha256()


def test_p1_criteria_digest_changes_with_every_constant():
    base = P1Criteria().digest()
    for kw in ({"budget": 25}, {"activity_min_seeds": 5}, {"fixed_rhos": (1.0, 8.0)},
               {"mmd_p_min": 0.1}, {"seeds": tuple(range(9))}, {"degenerate_k0_share": 0.7}):
        assert replace(P1Criteria(), **kw).digest() != base


def test_protocol_spec_version_and_p0_params_are_unchanged():
    assert SPEC_VERSION == "1.3"
    assert InterventionParams().digest() == "52f53b4c659a8d55dc218b5c8fde44b3bdfe951922baf12ff12c77b1e89d7509"


def test_p1_preregistration_text_is_frozen():
    """Pins the normative P1 text. Editing it after P1 data exists invalidates the campaign: a
    deliberate change must bump P1_SPEC_VERSION, update this pin and rerun everything it touches."""
    assert rules_sha256() == "d96b03131071ac1a8ad8c92c2dae0836bcd3a9f2357849ddf9c0341beb104401"
