"""The P1 experimental arms (SPEC v1.4 section 4). Every arm is `decide(view, incumbent, ctx)`.

All adaptive arms share ONE promotion function (`gate14.promote_star`): a candidate th* (whatever
produced it) must pass the frozen utility / envelope tests against D_gate and S_gate, must not be
worse than th_R, and otherwise th_R goes through the unchanged real-only rule. What differs between
arms is only how th* is produced:

  REAL_ONLY            th* = th_R                                  (delegates to the P0 `RealOnly`)
  CTRL-<op>            greedy sequential controller, op in {ROS, SMOTE, THRESH}
  FIXED-SMOTE-<rho>    one shot: rho * n_c synthetic rows for every class in I (the same need test)
  ALWAYS-SMOTE         rho = 1 for every class with n_c >= n_min, no need test, no search
  FIDGATE-SMOTE        FIXED-SMOTE-4 behind a permutation-calibrated MMD pre-filter
  negative controls    CTRL with wrong-class / Gaussian / shuffled rows; placebo dose on DDoS
  ablations            single switches of the controller (`ControllerOptions`), pooled sel/gate view
  references           REAL_ONLY_ALL_LABELS (P0 positive control), ORACLE_DOSE (candidates only,
                       never deployed, scored by the runner on the next window's E)

Arms never see E_t or S_report. They return the models they built in `shadow`; the runner scores
those AFTER `decide` has returned (candidate quality, SPEC v1.4 U2).
"""
from proteus.config import DEFAULT_N_JOBS  # noqa: F401 -- first import: caps BLAS/OMP threads

from dataclasses import dataclass, field, replace
from typing import Any, Optional

import numpy as np

from proteus.intervention.conditions import (
    LABEL_REGIME_ALL_NON_E, LABEL_REGIME_BUDGET, Frozen, RealOnly)
from proteus.intervention.controller import (
    PURPOSE_POOL, PURPOSE_PROMOTE_REAL, PURPOSE_PROMOTE_STAR, ControllerOptions, DataOperator,
    InterventionController, ThresholdOperator, sub_rng)
from proteus.intervention.generators import (
    DonorSMOTE, FeatureShuffle, GaussianBlob, GeneratorError, MMDPrefilter, RandomOversampler,
    SMOTEGenerator)
from proteus.intervention.gate14 import promote_star
from proteus.intervention.learner import (
    CandidateBuilder, TrainingAddition, compute_affected_region, compute_residual_sets,
    require_view)

PURPOSE_NONINF = 34
N_PERM_MMD = 100
DONOR_ROWS = 1000


@dataclass(frozen=True)
class ArmOutcome:
    model: Any
    promoted: bool
    branch: str                       # frozen | star | real_only | incumbent
    reason: str
    star_reason: str
    region: tuple
    eligible: Optional[tuple]
    theta_R: Any
    theta_star: Any
    k: int
    stop_reason: str
    trace: dict
    shadow: dict = field(default_factory=dict)      # name -> model (scored by the runner later)


def _no_region(incumbent, trace=None):
    return ArmOutcome(incumbent, False, "incumbent", "no_affected_region", "no_star", (), None,
                      None, None, 0, "no_affected_region", trace or {})


def _benign_index(view, params):
    return list(view.class_names).index(params.benign_label)


# ----------------------------------------------------------------------- generator factories
def gen_ros(c, view, params):
    return RandomOversampler()


def gen_smote(c, view, params):
    return SMOTEGenerator()


def gen_smote_mmd(c, view, params):
    return MMDPrefilter(SMOTEGenerator(), n_perm=N_PERM_MMD)


def gen_nc1(c, view, params):
    b = _benign_index(view, params)
    return DonorSMOTE(view.ref_X[view.ref_y == b][:DONOR_ROWS])


def gen_nc2(c, view, params):
    return GaussianBlob()


def gen_nc3(c, view, params):
    return FeatureShuffle()


# ----------------------------------------------------------------------------------- arms
class _Arm:
    name = "ARM"
    label_regime = LABEL_REGIME_BUDGET
    canary = True
    probe_pre_drift = False
    is_reference = False

    def _wrap(self, run, sd, extra_shadow=None):
        shadow = {}
        if run.theta_R is not None:
            shadow["theta_R"] = run.theta_R
        if run.theta_star is not None and run.theta_star is not run.theta_R:
            shadow["theta_star"] = run.theta_star
        shadow.update(extra_shadow or {})
        trace = {**run.region_info, "eligible": list(run.eligible), "k": run.k,
                 "stop_reason": run.stop_reason, "doses": {str(c): int(r) for c, r in run.doses.items()},
                 "operator": run.operator_info, "candidate_fits": run.candidate_fits,
                 "search": run.steps, "decision": sd.as_dict()}
        return ArmOutcome(sd.model, sd.promoted, sd.branch, sd.reason, sd.star_reason, run.region,
                          run.eligible, run.theta_R, run.theta_star, run.k, run.stop_reason, trace,
                          shadow)

    def _promote(self, view, incumbent, ctx, run):
        return promote_star(view, incumbent, run.theta_R, run.theta_star, run.region, ctx.params,
                            ctx.rng(PURPOSE_PROMOTE_STAR), ctx.rng(PURPOSE_PROMOTE_REAL),
                            ctx.anchor, ctx.rng(PURPOSE_NONINF))


class FrozenArm(_Arm):
    name = "FROZEN"
    canary = False

    def decide(self, view, incumbent, ctx):
        out = Frozen().decide(view, incumbent, ctx)
        return ArmOutcome(incumbent, False, "frozen", "frozen", "no_star", (), None, None, None, 0,
                          "frozen", {})


class RealOnlyArm(_Arm):
    """The P0 REAL_ONLY decision, verbatim (delegation), plus canary in the runner unless disabled."""

    def __init__(self, name="REAL_ONLY", canary=True, label_regime=LABEL_REGIME_BUDGET,
                 is_reference=False):
        self.name, self.canary, self.label_regime = name, canary, label_regime
        self.is_reference = is_reference

    def decide(self, view, incumbent, ctx):
        out = RealOnly().decide(view, incumbent, ctx)
        branch = "real_only" if out.promoted else "incumbent"
        shadow = {"theta_R": out.candidate} if out.candidate is not None else {}
        return ArmOutcome(out.model, out.promoted, branch, out.reason, "no_star", out.region,
                          out.eligible, out.candidate, None, 0, "real_only", out.trace, shadow)


class ControllerArm(_Arm):
    def __init__(self, name, op_factory, options=ControllerOptions(), canary=True,
                 pool_sel_gate=False, probe_pre_drift=False):
        self.name, self.op_factory, self.options = name, op_factory, options
        self.canary, self.pool_sel_gate, self.probe_pre_drift = canary, pool_sel_gate, probe_pre_drift

    @staticmethod
    def pooled(view):
        X = np.vstack([view.sel_X, view.gate_X])
        y = np.concatenate([view.sel_y, view.gate_y])
        return replace(view, sel_X=X, sel_y=y, gate_X=X, gate_y=y)

    def decide(self, view, incumbent, ctx):
        require_view(view)
        v = self.pooled(view) if self.pool_sel_gate else view
        run = InterventionController(self.op_factory(), self.options).run(
            v, incumbent, ctx, anchor=ctx.anchor)
        if run.theta_R is None:
            return _no_region(incumbent, run.region_info)
        return self._wrap(run, self._promote(v, incumbent, ctx, run))


class FixedDoseArm(_Arm):
    """One shot, no search: m_c = min(floor(rho n_c), M_cap) rows per class, scaled down jointly so
    that the synthetic share stays <= phi_max. classes: "eligible" (the need test I), "all"
    (every class with n_c >= n_min, no need test) or a tuple of class NAMES (forced placebo)."""

    def __init__(self, name, generator, rho, classes="eligible", canary=True):
        self.name, self.generator, self.rho, self.classes, self.canary = (
            name, generator, rho, classes, canary)

    def _classes(self, view, residual, region, params):
        n_c = np.bincount(view.real_y, minlength=len(view.class_names))
        if self.classes == "eligible":
            return tuple(residual.eligible)
        if self.classes == "all":
            return tuple(int(c) for c in np.flatnonzero(n_c >= params.n_min))
        ids = [list(view.class_names).index(n) for n in self.classes if n in view.class_names]
        return tuple(c for c in ids if n_c[c] >= params.n_min)

    def decide(self, view, incumbent, ctx):
        require_view(view)
        params = ctx.params
        info = compute_affected_region(view, incumbent, params, ctx.rng(10))
        trace = {"measurable": list(info.measurable), "region": list(info.region)}
        if not info.region:
            return _no_region(incumbent, trace)
        builder = CandidateBuilder(params, ctx.seed)
        theta_R = builder.build(view)
        residual = compute_residual_sets(view, theta_R, info.region, params, ctx.rng(11))
        classes = self._classes(view, residual, info.region, params)
        star, info_d = theta_R, {"classes": list(classes), "n_syn": 0, "scale": 1.0}
        if classes:
            op = DataOperator(self.name, self.generator)
            op.prepare(view, builder, theta_R, classes, params, ctx)
            want = {c: min(int(np.floor(self.rho * op.n_c[c])), params.m_cap, len(op.pools[c]))
                    for c in classes}
            tot = sum(want.values())
            n_real = len(view.real_y)
            scale = 1.0
            if tot and tot / (n_real + tot) > params.phi_max:
                scale = (params.phi_max / (1.0 - params.phi_max)) * n_real / tot
                want = {c: int(np.floor(m * scale)) for c, m in want.items()}
            parts = [(op.pools[c][:m], c) for c, m in sorted(want.items()) if m > 0]
            if parts:
                X = np.vstack([p for p, _ in parts]).astype(np.float32, copy=False)
                y = np.concatenate([np.full(len(p), c, dtype=np.int64) for p, c in parts])
                star = builder.build(view, TrainingAddition(X=X, y=y, source=self.name))
            info_d = {"classes": list(classes), "n_syn": int(sum(want.values())), "scale": scale,
                      "m": {str(c): int(m) for c, m in want.items()},
                      "fit_errors": {str(c): e for c, e in op.fit_errors.items()},
                      "mmd_p": op.describe({})["mmd_p"]}
        sd = promote_star(view, incumbent, theta_R, star, info.region, params,
                          ctx.rng(PURPOSE_PROMOTE_STAR), ctx.rng(PURPOSE_PROMOTE_REAL), ctx.anchor,
                          ctx.rng(PURPOSE_NONINF))
        shadow = {"theta_R": theta_R}
        if star is not theta_R:
            shadow["theta_star"] = star
        trace.update({"eligible": list(residual.eligible), "fixed": info_d, "k": 0,
                      "stop_reason": "fixed_dose", "decision": sd.as_dict()})
        return ArmOutcome(sd.model, sd.promoted, sd.branch, sd.reason, sd.star_reason, info.region,
                          residual.eligible, theta_R, star, 0, "fixed_dose", trace, shadow)


class OracleDoseRef(_Arm):
    """REFERENCE, never deployed and never a claim: builds th(rho) for every rho on the ladder (SMOTE,
    classes I) and hands them to the runner, which scores them on the next window's E. The per-window
    best rung is an upper bound on what any fixed dose could have achieved."""
    name = "ORACLE_DOSE"
    canary = False
    is_reference = True

    def decide(self, view, incumbent, ctx):
        require_view(view)
        params = ctx.params
        info = compute_affected_region(view, incumbent, params, ctx.rng(10))
        if not info.region:
            return _no_region(incumbent)
        builder = CandidateBuilder(params, ctx.seed)
        theta_R = builder.build(view)
        residual = compute_residual_sets(view, theta_R, info.region, params, ctx.rng(11))
        shadow = {"theta_R": theta_R}
        if residual.eligible:
            op = DataOperator(self.name, gen_smote)
            op.prepare(view, builder, theta_R, residual.eligible, params, ctx)
            for r, rho in enumerate(params.rho_ladder):
                if r == 0:
                    continue
                shadow[f"rho{rho:g}"] = op.build({c: r for c in residual.eligible})
        return ArmOutcome(incumbent, False, "incumbent", "reference_not_deployed", "no_star",
                          info.region, residual.eligible, theta_R, None, 0, "oracle_reference",
                          {"eligible": list(residual.eligible)}, shadow)


# ----------------------------------------------------------------------------------- registry
def _ctrl(name, op_factory, **kw):
    return ControllerArm(name, op_factory, **kw)


def make_arms(names=None):
    smote = lambda: DataOperator("SMOTE", gen_smote)
    arms = [
        FrozenArm(),
        RealOnlyArm("REAL_ONLY"),
        _ctrl("CTRL-ROS", lambda: DataOperator("ROS", gen_ros)),
        _ctrl("CTRL-THRESH", ThresholdOperator),
        _ctrl("CTRL-SMOTE", smote, probe_pre_drift=True),
        FixedDoseArm("FIXED-SMOTE-1", gen_smote, 1.0),
        FixedDoseArm("FIXED-SMOTE-4", gen_smote, 4.0),
        FixedDoseArm("ALWAYS-SMOTE", gen_smote, 1.0, classes="all"),
        FixedDoseArm("FIDGATE-SMOTE", gen_smote_mmd, 4.0),
        _ctrl("NC1-DONOR-SMOTE", lambda: DataOperator("NC1", gen_nc1)),
        _ctrl("NC2-GAUSSIAN", lambda: DataOperator("NC2", gen_nc2)),
        _ctrl("NC3-SHUFFLE", lambda: DataOperator("NC3", gen_nc3)),
        FixedDoseArm("NC4-PLACEBO-DDOS", gen_smote, 4.0, classes=("DDoS",)),
        _ctrl("ABL-NO-STEP-TEST", smote, options=ControllerOptions(step_test=False)),
        _ctrl("ABL-I-EQ-A", smote, options=ControllerOptions(need_test=False)),
        _ctrl("ABL-NO-STEP-SAFETY", smote, options=ControllerOptions(step_safety=False)),
        _ctrl("ABL-KMAX1", smote, options=ControllerOptions(k_cap=1)),
        _ctrl("ABL-MMD", lambda: DataOperator("SMOTE+MMD", gen_smote_mmd)),
        _ctrl("ABL-POOLED", smote, pool_sel_gate=True),
        _ctrl("ABL-NO-CANARY-CTRL", smote, canary=False),
        RealOnlyArm("ABL-NO-CANARY-REAL", canary=False),
        RealOnlyArm("REAL_ONLY_ALL_LABELS", label_regime=LABEL_REGIME_ALL_NON_E, is_reference=True),
        OracleDoseRef(),
    ]
    if names is None:
        return arms
    by = {a.name: a for a in arms}
    missing = [n for n in names if n not in by]
    if missing:
        raise KeyError(f"unknown arms: {missing}")
    return [by[n] for n in names]


ARM_NAMES = tuple(a.name for a in make_arms())
