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


LABEL_REGIME_BUDGET = "budget"          # only the B rows of L_t are labelled (the headline regime)
LABEL_REGIME_ALL_NON_E = "all_non_e"    # every non-E row of a window is labelled (positive control)


class Frozen:
    """Never adapts. Does not read the view; returns the incumbent object itself."""
    name = "FROZEN"
    label_regime = LABEL_REGIME_BUDGET

    def decide(self, view, incumbent, ctx):
        return Outcome(model=incumbent, promoted=False, reason="frozen", candidate=None,
                       region=(), eligible=None, trace={})


class RealOnly:
    """Fit a candidate on ref + real fit rows from the view, pass it through promotion."""
    name = "REAL_ONLY"
    label_regime = LABEL_REGIME_BUDGET

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


class RealOnlyAllLabels(RealOnly):
    """POSITIVE CONTROL, never a headline method (SPEC v1.1 section 4, "refs").

    Decision logic is identical to REAL_ONLY (same learner, same promotion rule, same envelope
    anchor, same thresholds). Only the label regime differs: every non-E row of every window is
    labelled (instead of the B rows of L_t), arriving with the same one-window delay and assigned
    to fit / sel / gate by the same group hash. E_t, S_report and S_cal stay unreachable. The
    labelled rows of the budget regime are a strict subset of this regime's, on the same manifest.
    It reproduces the oracle-label regime of the old Stage-7 headline under the new protocol, so
    P0's V4 can check that the learner can absorb new classes when labels are abundant.

    Known caveat, reported in every result file: the real buffer is a 5000-row FIFO and this regime
    adds ~1260 fit rows per window, so it evicts early rows. The strict nesting
    D_ref subset-of D_real subset-of candidate therefore holds for the *current* buffer contents
    only, and the control is allowed to forget old real rows. That is a property of the control,
    not a defect: it is a reference point, not an arm of any comparison."""
    name = "REAL_ONLY_ALL_LABELS"
    label_regime = LABEL_REGIME_ALL_NON_E
    is_positive_control = True
