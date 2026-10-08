"""FROZEN and REAL_ONLY conditions, parameter pinning, anti-leakage boundaries and a full
replay on synthetic data (SPEC v1.0 sections 1.5, 4, 6)."""
import ast
import importlib
import json
from dataclasses import fields

import numpy as np
import pytest
from sklearn.metrics import f1_score

from proteus.intervention.cache import DataBundle, hash_rows
from proteus.intervention.conditions import DecisionContext, Frozen, Outcome, RealOnly
from proteus.intervention.learner import CandidateBuilder
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import (
    SPEC_VERSION, ControllerView, ScenarioConfig, StreamReplay, StreamState, build_partitions)
from tests.test_intervention_learner import make_learnable_view
from tests.test_intervention_protocol import _make_data


def params(**kw):
    return InterventionParams(benign_label="benign", rf_n_estimators=25, **kw)  # 25 trees: speed


def ctx(t=3, seed=0, p=None, anchor=None):
    return DecisionContext(t=t, seed=seed, params=p or params(), anchor=anchor)


def base_model(view, seed=0):
    """theta_0 = theta_base = fit(D_ref) (SPEC v1.1, D1)."""
    return CandidateBuilder(params(), seed).build_base(view)


# ----------------------------------------------------------------------------- parameters
def test_defaults_match_the_frozen_spec_section_1_5():
    p = InterventionParams()
    assert (p.alpha, p.n_boot, p.s_min, p.n_min) == (0.05, 2000, 5, 5)
    assert (p.eps_def, p.eta, p.eps_ni, p.eps_s, p.eps_fpr) == (0.05, 0.02, 0.01, 0.01, 0.005)
    assert p.rho_ladder == (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
    assert (p.m_cap, p.phi_max, p.k_max, p.rf_n_estimators) == (2000, 0.5, 10, 100)
    assert p.promotion_alpha == pytest.approx(0.025)
    assert p.step_alpha == pytest.approx(0.005)


def test_param_digest_changes_with_any_threshold_and_params_are_immutable():
    assert InterventionParams().digest() == InterventionParams().digest()
    assert InterventionParams().digest() != InterventionParams(eps_fpr=0.006).digest()
    with pytest.raises(Exception):
        InterventionParams().eps_s = 0.5


# ----------------------------------------------------------------------------- FROZEN
def test_frozen_returns_the_incumbent_untouched_and_never_reads_the_view():
    class Boom:
        def __getattribute__(self, name):
            raise AssertionError(f"FROZEN touched the view ({name})")

    view = make_learnable_view()
    inc = base_model(view)
    probe = np.random.default_rng(4).normal(size=(300, 4)).astype(np.float32) * 6
    before = inc.predict(probe).copy()
    out = Frozen().decide(Boom(), inc, ctx())
    assert isinstance(out, Outcome)
    assert out.model is inc and out.candidate is None
    assert not out.promoted and out.reason == "frozen" and out.region == ()
    assert np.array_equal(inc.predict(probe), before)


# ----------------------------------------------------------------------------- REAL_ONLY
def test_real_only_adapts_when_the_evidence_is_sufficient():
    view = make_learnable_view()
    inc = base_model(view)
    out = RealOnly().decide(view, inc, ctx(anchor=inc))
    assert out.promoted and out.reason == "promoted"
    assert out.region == (1, 2)       # b is unseen (F1 0) and a loses precision to it
    assert out.model is out.candidate and out.model is not inc
    assert out.eligible == ()                       # nothing left to fix after real adaptation
    assert out.trace["eligible_f1_diagnostic"] == []     # logged next to the recall-based set
    assert out.trace["decision"]["report"]["utility_gain_lcb"] > 0.5
    new_b = np.random.default_rng(8).normal(size=(100, 4)).astype(np.float32) + 12.0
    assert (out.model.predict(new_b) == 2).mean() > 0.95
    assert (inc.predict(new_b) == 2).mean() == 0.0


def test_real_only_keeps_the_incumbent_when_nothing_is_measurable():
    view = make_learnable_view(gate_counts={0: 80, 1: 3, 2: 3})   # only benign is measurable
    inc = base_model(view)
    out = RealOnly().decide(view, inc, ctx(anchor=inc))
    assert not out.promoted and out.reason == "no_affected_region"
    assert out.model is inc and out.candidate is None and out.region == ()


def test_real_only_rejects_a_harmful_candidate_via_promotion():
    # real fit rows with flipped labels for the stable classes make the candidate worse on S
    view = make_learnable_view()
    bad_y = np.where(view.real_y == 1, 0, view.real_y)          # class a relabelled benign
    poisoned = ControllerView(**{**{f.name: getattr(view, f.name) for f in fields(view)},
                                 "real_y": bad_y})
    inc = base_model(view)
    out = RealOnly().decide(poisoned, inc, ctx(anchor=inc))
    assert not out.promoted and out.model is inc
    assert out.reason.startswith(("utility_", "envelope_"))
    assert out.candidate is not None                     # it was built, then rejected


def test_real_only_requires_the_fixed_anchor():
    view = make_learnable_view()
    inc = base_model(view)
    with pytest.raises(ValueError):
        RealOnly().decide(view, inc, ctx(anchor=None))


def test_real_only_rejects_non_views():
    view = make_learnable_view()
    inc = base_model(view)
    with pytest.raises(TypeError):
        RealOnly().decide({"ref_X": 1}, inc, ctx(anchor=inc))


def test_real_only_never_reads_the_step_selection_stable_set():
    view = make_learnable_view()
    inc = base_model(view)

    class Audited(ControllerView):
        log = []

        def __getattribute__(self, name):
            if name in ControllerView.__dataclass_fields__:
                Audited.log.append(name)
            return super().__getattribute__(name)

    audited = Audited(**{f.name: getattr(view, f.name) for f in fields(view)})
    Audited.log.clear()
    RealOnly().decide(audited, inc, ctx(anchor=inc))
    touched = set(Audited.log)
    assert touched.isdisjoint({"s_sel_X", "s_sel_y"})
    assert {"ref_X", "ref_y", "real_X", "real_y", "gate_X", "gate_y"} <= touched


def test_decisions_are_deterministic_for_the_same_seed_and_step():
    view = make_learnable_view()
    inc = base_model(view)
    a = RealOnly().decide(view, inc, ctx(t=4, seed=2, anchor=inc))
    b = RealOnly().decide(view, inc, ctx(t=4, seed=2, anchor=inc))
    assert json.dumps(a.trace, sort_keys=True) == json.dumps(b.trace, sort_keys=True)
    probe = np.random.default_rng(1).normal(size=(200, 4)).astype(np.float32) * 8
    assert np.array_equal(a.model.predict(probe), b.model.predict(probe))
    cand = CandidateBuilder(params(), 2).build(view)
    assert np.array_equal(cand.predict(probe), a.candidate.predict(probe))


# ----------------------------------------------------------------------------- boundaries
FORBIDDEN_NAMES = {
    "build_initial_model", "DataBundle", "PartitionManifest", "StreamState", "StreamReplay", "StreamStep", "WindowSpec",
    "build_partitions", "load_cache", "detect_drift", "e_idx", "u_idx", "l_idx", "l_role",
    "s_cal_idx", "s_report_idx", "s_sel_idx", "s_gate_idx", "train_idx", "ref_idx", "manifest",
    "windows"}
FORBIDDEN_MODULE_PARTS = ("drift", "fidelity", "closed_loop", "evaluate_full", "gan_full",
                          "cache", "data_full")


@pytest.mark.parametrize("module", ["learner", "promotion", "conditions", "params"])
def test_decision_modules_have_no_code_path_to_data_outside_the_view(module):
    path = importlib.import_module(f"proteus.intervention.{module}").__file__
    tree = ast.parse(open(path).read())
    names, modules = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.update({node.name, node.asname or node.name})
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
        elif isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
    assert not (names & FORBIDDEN_NAMES), f"{module} references {sorted(names & FORBIDDEN_NAMES)}"
    bad = [m for m in modules if any(part in m for part in FORBIDDEN_MODULE_PARTS)]
    assert not bad, f"{module} imports {bad}"


def _idents(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.update({node.name, node.asname or node.name})
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def test_no_free_form_base_fit_anywhere_in_the_package():
    """SPEC v1.1 D1 audit: theta_0 can only be built by CandidateBuilder.build_base(view); no
    module other than protocol.py (which defines the partition) even names TRAIN's indices, and
    the single model-fitting call site in the whole package is learner._fit_rf."""
    import pathlib
    pkg = pathlib.Path(importlib.import_module("proteus.intervention").__file__).parent
    fit_sites = []
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text())
        idents = _idents(tree)
        assert "build_initial_model" not in idents, path.name
        if path.name != "protocol.py":
            assert "train_idx" not in idents, f"{path.name} references TRAIN indices"
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call)]:
                if isinstance(call.func, ast.Attribute) and call.func.attr == "fit":
                    fit_sites.append((path.name, fn.name))
    assert fit_sites == [("learner.py", "_fit_rf")], fit_sites
    learner_tree = ast.parse((pkg / "learner.py").read_text())
    callers = {fn.name for fn in ast.walk(learner_tree) if isinstance(fn, ast.FunctionDef)
               for c in ast.walk(fn) if isinstance(c, ast.Call)
               and isinstance(c.func, ast.Name) and c.func.id == "_fit_rf"}
    assert callers == {"build_base", "build"}, callers


def test_spec_version_is_1_3():
    assert SPEC_VERSION == "1.3"


def test_the_view_still_exposes_exactly_the_frozen_fields():
    assert set(ControllerView.__dataclass_fields__) == {
        "ref_X", "ref_y", "real_X", "real_y", "sel_X", "sel_y", "gate_X", "gate_y",
        "s_sel_X", "s_sel_y", "s_gate_X", "s_gate_y", "class_names"}


# ----------------------------------------------------------------------------- full replay
CFG = ScenarioConfig("I", ("Monday", "Tuesday", "Wednesday", "Thursday"), ("Friday",),
                     window_size=1500, n_pre_windows=2, n_post_windows=5, budget=600,
                     s_size=800, ref_size=1500, real_buffer_cap=3000, eval_buffer_cap=3000)


@pytest.fixture(scope="module")
def separable_data():
    d = _make_data(0)
    X = (d.X + 2.0 * d.y[:, None].astype(np.float32)).astype(np.float32)
    return DataBundle(X=X, y=d.y, day=d.day, group=hash_rows(X),
                      class_names=["benign", "c1", "c2", "c3", "c4", "c5"],
                      feature_names=d.feature_names)


def _replay(data, condition, seed=0):
    manifest = build_partitions(data, CFG, seed=seed)
    p = params()
    state = StreamState(data, manifest)
    model = CandidateBuilder(p, seed).build_base(state.view())      # theta_0 = fit(D_ref)
    initial = anchor = model
    outcomes = []
    for step in StreamReplay(manifest):
        state.ingest(step)
        if step.phase == "post":                       # oracle trigger: every post-drift window
            out = condition.decide(state.view(), model, DecisionContext(step.t, seed, p, anchor))
            model = out.model
            outcomes.append(out)
    return manifest, initial, model, outcomes


def _post_e_f1(data, manifest, model, classes=(4, 5)):
    e = np.concatenate([w.e_idx for w in manifest.windows if w.phase == "post"])
    return f1_score(data.y[e], model.predict(data.X[e]), labels=list(classes), average=None,
                    zero_division=0)


def test_replay_frozen_never_changes_and_real_only_recovers_the_new_classes(separable_data):
    manifest, initial, frozen_final, f_out = _replay(separable_data, Frozen())
    assert frozen_final is initial and not any(o.promoted for o in f_out)
    _, _, real_final, r_out = _replay(separable_data, RealOnly())
    assert any(o.promoted for o in r_out), [o.reason for o in r_out]
    first = next(o for o in r_out if o.promoted)
    assert {4, 5} & set(first.region)
    assert _post_e_f1(separable_data, manifest, frozen_final).max() < 0.05
    assert _post_e_f1(separable_data, manifest, real_final).min() > 0.8


def test_replay_decisions_are_identical_across_repeated_runs(separable_data):
    _, _, m1, o1 = _replay(separable_data, RealOnly(), seed=5)
    _, _, m2, o2 = _replay(separable_data, RealOnly(), seed=5)
    assert [json.dumps(o.trace, sort_keys=True) for o in o1] == \
           [json.dumps(o.trace, sort_keys=True) for o in o2]
    probe = separable_data.X[:500]
    assert np.array_equal(m1.predict(probe), m2.predict(probe))
