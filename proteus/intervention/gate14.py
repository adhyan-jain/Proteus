"""SPEC v1.4 promotion of a controller candidate th* and the canary (J.1 item 1, J.2).

This module ADDS to `promotion.py` without touching it (the P0 code path stays byte-identical):

  promote_star(view, incumbent, theta_R, theta_star, region, params, rng_*, anchor) -> StarDecision
      J.1 with the v1.4 split of the spec's overloaded "theta_0" into the current INCUMBENT (utility
      comparison) and the fixed ANCHOR theta_base = fit(D_ref) (envelope). Evidence: D_gate and S_gate
      only. Promote th* iff
         (1) sanity, (2) LCB_{a/2}(U(th*) - U(incumbent); D_gate) > 0, (3) the envelope against the
         anchor passes (UCB_{a/2} <= eps for every quantity, the frozen v1.3 rule), and
         (4) th* is not worse than th_R: the POINT gain U(th*) - U(th_R) > 0 and
             LCB_{a/2}(U(th*) - U(th_R)) >= -eps_ni.
      Otherwise th_R goes through the unchanged real-only rule (`promotion.promote`), and otherwise
      the incumbent stays. Every arm (controller, fixed-dose, always-on, ...) passes through this one
      function, so the gate is identical across conditions.

  canary(theta_new, theta_prev, anchor, X, y, region, params, rng, benign=, n_classes=)
      J.2 on the labels that ARRIVE after the promotion (never used to build or promote theta_new).
      Roll back iff UCB_a(U(new) - U(prev)) < 0 (significantly worse) or the benign-FPR envelope is
      ESTABLISHED broken on those labels (LCB_a(FPR(new) - FPR(anchor)) > eps_FPR, the v1.3 meaning of
      "violated"). Missing evidence never triggers a rollback.
"""
import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from proteus.intervention.learner import require_view
from proteus.intervention.metrics import (
    benign_fpr_conf, bootstrap_confusions, confusion, lcb, region_utility_conf, ucb)
from proteus.intervention.promotion import (
    CandidateReport, Decision, evaluate_candidate, promote, _envelope_reason)

STAR_REASONS = ("promoted", "no_star", "sanity", "utility_unmeasurable", "utility_no_gain",
                "utility_inconclusive", "envelope_unverifiable", "envelope_violated",
                "envelope_inconclusive", "star_no_gain_over_real", "star_inferior_to_real")


@dataclass(frozen=True)
class StarDecision:
    model: Any
    promoted: bool
    branch: str                     # "star" | "real_only" | "incumbent"
    reason: str                     # why the FINAL outcome is what it is
    star_reason: str                # why th* was / was not promoted ("no_star" if there was none)
    star_report: Optional[CandidateReport]
    noninferiority: dict
    real_decision: Optional[Decision]

    def as_dict(self):
        from dataclasses import asdict
        return {"promoted": self.promoted, "branch": self.branch, "reason": self.reason,
                "star_reason": self.star_reason, "noninferiority": self.noninferiority,
                "star_report": asdict(self.star_report) if self.star_report is not None else None,
                "real_decision": self.real_decision.as_dict() if self.real_decision else None}


def _star_vs_real(view, theta_R, theta_star, region, params, rng):
    """Paired comparison of th* with th_R on D_gate (point gain and LCB at promotion alpha)."""
    k = len(view.class_names)
    if not len(view.gate_y) or not region:
        return {"point": float("nan"), "lcb": float("nan")}
    p_r, p_s = theta_R.predict(view.gate_X), theta_star.predict(view.gate_X)
    conf_r, conf_s = bootstrap_confusions(view.gate_y, [p_r, p_s], k, params.n_boot, rng)
    gain = region_utility_conf(conf_s, region) - region_utility_conf(conf_r, region)
    point = float(region_utility_conf(confusion(view.gate_y, p_s, k), region)
                  - region_utility_conf(confusion(view.gate_y, p_r, k), region))
    return {"point": point, "lcb": lcb(gain, params.promotion_alpha)}


def promote_star(view, incumbent, theta_R, theta_star, region, params, rng_star, rng_real, anchor,
                 rng_noninf=None) -> StarDecision:
    require_view(view)
    if theta_R is None or not region:
        return StarDecision(incumbent, False, "incumbent", "no_affected_region", "no_star", None,
                            {}, None)
    star_reason, star_report, noninf = "no_star", None, {}
    if theta_star is not None and theta_star is not theta_R:
        star_report = evaluate_candidate(view, incumbent, theta_star, region, params, rng_star,
                                         anchor)
        if not star_report.sanity_ok:
            star_reason = "sanity"
        elif not star_report.utility_ok:
            star_reason = f"utility_{star_report.utility_status}"
        elif not star_report.envelope_ok:
            star_reason = _envelope_reason(star_report)
        else:
            noninf = _star_vs_real(view, theta_R, theta_star, region, params,
                                   rng_noninf if rng_noninf is not None else rng_star)
            if not (noninf["point"] > 0.0):
                star_reason = "star_no_gain_over_real"
            elif not (noninf["lcb"] >= -params.eps_ni):
                star_reason = "star_inferior_to_real"
            else:
                star_reason = "promoted"
        if star_reason == "promoted":
            return StarDecision(theta_star, True, "star", "promoted", "promoted", star_report,
                                noninf, None)
    real = promote(view, incumbent, theta_R, region, params, rng_real, anchor)
    return StarDecision(real.model, real.promoted, "real_only" if real.promoted else "incumbent",
                        real.reason, star_reason, star_report, noninf, real)


# ----------------------------------------------------------------------------------- canary
@dataclass(frozen=True)
class CanaryDecision:
    rollback: bool
    reason: str                     # keep | utility_worse | fpr_envelope_violated | no_evidence
    stats: dict


def canary(theta_new, theta_prev, anchor, X, y, region, params, rng, *, benign,
           n_classes) -> CanaryDecision:
    a = params.alpha
    if not len(y) or not region:
        return CanaryDecision(False, "no_evidence", {"n_rows": int(len(y))})
    k = int(n_classes)
    p_new, p_prev = theta_new.predict(X), theta_prev.predict(X)
    preds = [p_new, p_prev] + ([anchor.predict(X)] if anchor is not None else [])
    confs = bootstrap_confusions(y, preds, k, params.n_boot, rng)
    du = region_utility_conf(confs[0], region) - region_utility_conf(confs[1], region)
    du_point = float(region_utility_conf(confusion(y, p_new, k), region)
                     - region_utility_conf(confusion(y, p_prev, k), region))
    stats = {"n_rows": int(len(y)), "utility_diff_point": du_point, "utility_diff_ucb": ucb(du, a)}
    worse = bool(np.isfinite(stats["utility_diff_ucb"]) and stats["utility_diff_ucb"] < 0.0)
    violated = False
    if anchor is not None:
        d = benign_fpr_conf(confs[0], benign) - benign_fpr_conf(confs[2], benign)
        stats["fpr_vs_anchor_lcb"] = lcb(d, a)
        stats["n_benign"] = int((np.asarray(y) == benign).sum())
        violated = bool(np.isfinite(stats["fpr_vs_anchor_lcb"])
                        and stats["fpr_vs_anchor_lcb"] > params.eps_fpr)
    reason = "utility_worse" if worse else ("fpr_envelope_violated" if violated else "keep")
    return CanaryDecision(worse or violated, reason, stats)
