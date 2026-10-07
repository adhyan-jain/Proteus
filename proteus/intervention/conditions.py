"""Adaptation conditions (SPEC v1.0 section 4, baseline set): FROZEN and REAL_ONLY.

A condition is `decide(view, incumbent, ctx) -> Outcome`. Later conditions (controller with a
generator, fixed-dose, oracle references) implement the same protocol, so the experiment loop and
the promotion rule never change when an intervention operator is added.
"""
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import numpy as np

from proteus.intervention.learner import (
    CandidateBuilder, compute_affected_region, compute_residual_sets, require_view)
from proteus.intervention.params import InterventionParams
from proteus.intervention.promotion import promote
from proteus.intervention.protocol import ControllerView

_PURPOSE_REGION, _PURPOSE_ELIGIBLE, _PURPOSE_PROMOTE = 10, 11, 12


@dataclass(frozen=True)
class DecisionContext:
    """Everything a condition may use besides the view: the step index, the run seed, the frozen
    parameters and the fixed safety anchor theta_base = fit(D_ref) (SPEC v1.1, D2; a model, not
    data). All randomness is derived from (seed, t, purpose)."""
    t: int
    seed: int
    params: InterventionParams
    anchor: Any = None

    def rng(self, purpose: int):
        return np.random.default_rng([self.seed, self.t, purpose])


@dataclass(frozen=True)
class Outcome:
    model: Any                      # the model to deploy from the next window
    promoted: bool
    reason: str
    candidate: Optional[Any]        # the fitted candidate, promoted or not (None if not built)
    region: tuple                   # affected region A
    eligible: Optional[tuple]       # I (recall-based): residual deficiency after real-only
    trace: dict                     # JSON-safe diagnostics for the result file


class Condition(Protocol):
    name: str

    def decide(self, view: ControllerView, incumbent: Any, ctx: DecisionContext) -> Outcome: ...


class Frozen:
    """Never adapts. Does not read the view; returns the incumbent object itself."""
    name = "FROZEN"

    def decide(self, view, incumbent, ctx):
        return Outcome(model=incumbent, promoted=False, reason="frozen", candidate=None,
                       region=(), eligible=None, trace={})


class RealOnly:
    """Fit a candidate on ref + real fit rows from the view, pass it through promotion."""
    name = "REAL_ONLY"

    def decide(self, view, incumbent, ctx):
        require_view(view)
        if ctx.anchor is None:
            raise ValueError("REAL_ONLY needs DecisionContext.anchor (theta_base = fit(D_ref))")
        params = ctx.params
        info = compute_affected_region(view, incumbent, params, ctx.rng(_PURPOSE_REGION))
        trace = {"measurable": list(info.measurable), "region": list(info.region),
                 "deficiency_lcb": {str(c): v for c, v in info.deficiency_lcb.items()}}
        if not info.region:
            return Outcome(incumbent, False, "no_affected_region", None, (), None, trace)

        candidate = CandidateBuilder(params, ctx.seed).build(view)
        residual = compute_residual_sets(view, candidate, info.region, params,
                                         ctx.rng(_PURPOSE_ELIGIBLE))
        decision = promote(view, incumbent, candidate, info.region, params,
                           ctx.rng(_PURPOSE_PROMOTE), ctx.anchor)
        trace.update({"eligible": list(residual.eligible),
                      "eligible_f1_diagnostic": list(residual.f1_diagnostic),
                      "n_train_rows": candidate.n_train_rows, "decision": decision.as_dict()})
        return Outcome(decision.model, decision.promoted, decision.reason, candidate,
                       info.region, residual.eligible, trace)
