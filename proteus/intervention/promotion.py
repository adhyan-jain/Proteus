"""Candidate promotion: a pure function of (view, incumbent, candidate, region, params, rng, anchor).

Rule implemented (SPEC v1.1 section 2, J.1 item 2, for a real-only candidate theta_R). All three
bounds use alpha_p = params.promotion_alpha = alpha / 2 and are paired-bootstrap bounds over the
promotion-only sets D_gate and S_gate (class-stratified, models scored on identical rows):

  promote the candidate iff
    (1) it passes the sanity check (finite probabilities summing to 1, matching class width,
        classes inside the view's range);
    (2) the affected region A is non-empty;
    (3) utility, against the CURRENT INCUMBENT:
          LCB_{alpha_p}( U(cand; D_gate) - U(incumbent; D_gate) ) > 0,   U = mean F1 over A;
    (4) envelope, against the FIXED ANCHOR theta_base = fit(D_ref) (v1.1, D2) -- never against the
        moving incumbent, so stable degradation cannot accumulate across promotions:
          UCB_{alpha_p}( stable macro-F1 drop on S_gate )                  <= eps_s
          UCB_{alpha_p}( benign FPR increase on S_gate )                   <= eps_fpr
          UCB_{alpha_p}( benign FPR increase on D_gate's benign rows )     <= eps_fpr
        an undefined quantity (e.g. no benign rows) is a violation (fail closed).
  otherwise the incumbent is kept.

The reason (v1.1, D3) is the first failing criterion in the order sanity -> no_affected_region ->
utility_* -> envelope_*; every failing criterion is listed in `CandidateReport.failed`.
  utility_unmeasurable   no D_gate evidence, or the bound is undefined
  utility_no_gain        point gain <= 0
  utility_inconclusive   point gain > 0 but its LCB <= 0
  envelope_violated      (v1.3) some degradation is statistically ESTABLISHED beyond its epsilon:
                         the one-sided lower confidence bound LCB_{alpha/2} exceeds epsilon
  envelope_unverifiable  some quantity is undefined (no outranking violation)
  envelope_inconclusive  no UCB-based pass, but no established violation either (LCB <= epsilon):
                         the evidence cannot decide, e.g. one flipped row among ~30 benign rows
Among envelope labels a known violation outranks missing evidence. The labels only say WHY a
candidate was rejected; they never change whether it was (v1.3 changed labels, not decisions: the
promote/reject rule still requires UCB_{alpha/2} <= epsilon for every envelope quantity).
v1.2 labelled "violated" from the POINT estimate, which at small n is a granularity artifact.

D_sel and S_sel are never read here (they steer step decisions, not promotion). The function has
no access to reporting rows, unlabelled rows, the drift-detector reference or future windows: its
only data argument is a `ControllerView`. The anchor is a model, not data.

Deviation from the spec text: the spec reuses `drift_daemon.CandidateValidationGate` for the
shape/NaN/sum checks. That gate requires predict_proba width == number of classes, which a
random forest trained on a class subset never has, and importing it drags in the deployment
stack, so the same three checks are re-implemented in `sanity_check` below.
"""
from dataclasses import dataclass, asdict
from typing import Any, Optional

import numpy as np

from proteus.intervention.learner import require_view
from proteus.intervention.metrics import (
    benign_fpr_conf, bootstrap_confusions, confusion, lcb, region_utility_conf,
    stable_macro_f1_conf, ucb)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import ControllerView

REASONS = ("promoted", "sanity", "no_affected_region", "utility_unmeasurable",
           "utility_no_gain", "utility_inconclusive", "envelope_unverifiable",
           "envelope_violated", "envelope_inconclusive")

_NAN = float("nan")


@dataclass(frozen=True)
class CandidateReport:
    sanity_ok: bool
    sanity_msg: str
    # utility (vs the incumbent, on D_gate)
    utility_gain_point: float
    utility_gain_lcb: float
    # envelope (vs the anchor): point estimate and upper confidence bound of each degradation
    delta_stable_f1_point: float
    delta_stable_f1_ucb: float
    delta_fpr_stable_point: float
    delta_fpr_stable_ucb: float
    delta_fpr_current_point: float
    delta_fpr_current_ucb: float
    # per-criterion status
    utility_status: str            # ok | unmeasurable | no_gain | inconclusive | not_evaluated
    stable_f1_status: str          # ok | unverifiable | violated | inconclusive | not_evaluated
    fpr_stable_status: str
    fpr_current_status: str
    failed: tuple
    # support behind every statistic
    n_gate_rows: int
    gate_support: tuple            # rows per class in D_gate
    n_gate_region_rows: int        # D_gate rows whose true class is in A
    n_gate_benign: int
    n_s_gate_rows: int
    s_gate_support: tuple          # rows per class in S_gate
    n_s_gate_benign: int
    n_stable_classes: int          # |C_S|
    # v1.3: raw quantities behind each envelope label, so a reader can see sample size (above),
    # point estimate, both bounds, epsilon and the label without recomputing anything.
    delta_stable_f1_lcb: float = float("nan")      # LCB_{alpha/2} of the stable macro-F1 drop
    delta_fpr_stable_lcb: float = float("nan")     # LCB_{alpha/2} of the benign-FPR rise on S_gate
    delta_fpr_current_lcb: float = float("nan")    # LCB_{alpha/2} of the benign-FPR rise on D_gate
    eps_stable_f1: float = float("nan")            # the preregistered epsilons the bounds meet
    eps_fpr: float = float("nan")
    envelope_alpha: float = float("nan")           # one-sided level of every bound (alpha / 2)

    @property
    def utility_ok(self):
        return self.utility_status == "ok"

    @property
    def stable_f1_ok(self):
        return self.stable_f1_status == "ok"

    @property
    def fpr_stable_ok(self):
        return self.fpr_stable_status == "ok"

    @property
    def fpr_current_ok(self):
        return self.fpr_current_status == "ok"

    @property
    def envelope_ok(self):
        return self.stable_f1_ok and self.fpr_stable_ok and self.fpr_current_ok

    @property
    def envelope_statuses(self):
        return (self.stable_f1_status, self.fpr_stable_status, self.fpr_current_status)


@dataclass(frozen=True)
class Decision:
    promoted: bool
    reason: str
    model: Any                       # the candidate if promoted, else the incumbent
    report: Optional[CandidateReport]

    def as_dict(self):
        return {"promoted": self.promoted, "reason": self.reason,
                "report": asdict(self.report) if self.report is not None else None}


def sanity_check(model, n_features, n_classes):
    try:
        x = np.zeros((5, n_features), dtype=np.float32)
        pred = np.asarray(model.predict(x))
        proba = np.asarray(model.predict_proba(x))
    except Exception as e:  # noqa: BLE001 -- any failure means the candidate is unusable
        return False, f"inference failed: {e}"
    if len(pred) != 5:
        return False, "prediction length mismatch"
    if proba.ndim != 2 or proba.shape != (5, len(model.classes_)):
        return False, "probability width does not match the model's classes"
    if not np.isfinite(proba).all():
        return False, "NaN or Inf probabilities"
    if not np.allclose(proba.sum(axis=1), 1.0, atol=1e-3):
        return False, "probabilities do not sum to 1"
    classes = np.asarray(model.classes_)
    if classes.min() < 0 or classes.max() >= n_classes:
        return False, "model has classes outside the view's class range"
    return True, "ok"


def _utility_status(point, lcb_value):
    if not (np.isfinite(point) and np.isfinite(lcb_value)):
        return "unmeasurable"
    if lcb_value > 0.0:
        return "ok"
    return "no_gain" if point <= 0.0 else "inconclusive"


def _envelope_status(lcb_value, ub_value, eps):
    """v1.3. ok: UCB <= eps (safety demonstrated, the only promotable state). violated: the LCB
    exceeds eps, i.e. degradation beyond eps is statistically established. Anything else with an
    undefined bound is unverifiable; a defined UCB above eps without an established violation is
    inconclusive. The point estimate no longer decides the label."""
    if not np.isfinite(ub_value):
        return "unverifiable"
    if ub_value <= eps:
        return "ok"
    if np.isfinite(lcb_value) and lcb_value > eps:
        return "violated"
    return "inconclusive"


def _benign_fpr_point(y, pred, k, benign):
    return float(benign_fpr_conf(confusion(y, pred, k), benign))


def evaluate_candidate(view: ControllerView, incumbent, candidate, region,
                       params: InterventionParams, rng, anchor) -> CandidateReport:
    """Compute the promotion statistics. Pure; reads only D_gate, S_gate and the class set of
    D_ref (to know which classes are 'pre-drift')."""
    require_view(view)
    if anchor is None:
        raise ValueError("promotion needs the fixed anchor model theta_base (SPEC v1.1, D2)")
    k = len(view.class_names)
    a = params.promotion_alpha
    benign = list(view.class_names).index(params.benign_label)

    gate_support = np.bincount(view.gate_y, minlength=k)
    s_support = np.bincount(view.s_gate_y, minlength=k)
    stable = [int(c) for c in np.unique(view.ref_y) if s_support[c] >= params.s_min]
    support = dict(
        n_gate_rows=int(len(view.gate_y)), gate_support=tuple(int(v) for v in gate_support),
        n_gate_region_rows=int(sum(gate_support[c] for c in region)),
        n_gate_benign=int(gate_support[benign]), n_s_gate_rows=int(len(view.s_gate_y)),
        s_gate_support=tuple(int(v) for v in s_support), n_s_gate_benign=int(s_support[benign]),
        n_stable_classes=len(stable))

    eps = dict(eps_stable_f1=params.eps_s, eps_fpr=params.eps_fpr, envelope_alpha=a)
    sane, msg = sanity_check(candidate, view.ref_X.shape[1], k)
    if not sane:
        return CandidateReport(
            False, msg, _NAN, _NAN, _NAN, _NAN, _NAN, _NAN, _NAN, _NAN, "not_evaluated",
            "not_evaluated", "not_evaluated", "not_evaluated", ("sanity",), **support, **eps)

    # drift-side evidence: D_gate (utility vs incumbent; benign FPR vs anchor)
    gain_point = gain_lcb = fpr_cur_point = fpr_cur_ucb = fpr_cur_lcb = _NAN
    if len(view.gate_y) and region:
        p_inc, p_cand, p_anc = (m.predict(view.gate_X) for m in (incumbent, candidate, anchor))
        conf_inc, conf_cand, conf_anc = bootstrap_confusions(
            view.gate_y, [p_inc, p_cand, p_anc], k, params.n_boot, rng)
        gain = region_utility_conf(conf_cand, region) - region_utility_conf(conf_inc, region)
        gain_lcb = lcb(gain, a)
        gain_point = float(region_utility_conf(confusion(view.gate_y, p_cand, k), region)
                           - region_utility_conf(confusion(view.gate_y, p_inc, k), region))
        fpr_cur = benign_fpr_conf(conf_cand, benign) - benign_fpr_conf(conf_anc, benign)
        fpr_cur_ucb, fpr_cur_lcb = ucb(fpr_cur, a), lcb(fpr_cur, a)
        fpr_cur_point = (_benign_fpr_point(view.gate_y, p_cand, k, benign)
                         - _benign_fpr_point(view.gate_y, p_anc, k, benign))

    # stable-traffic evidence: S_gate, vs the anchor
    ds_point = ds_ucb = fpr_s_point = fpr_s_ucb = ds_lcb = fpr_s_lcb = _NAN
    if len(view.s_gate_y) and stable:
        p_anc, p_cand = anchor.predict(view.s_gate_X), candidate.predict(view.s_gate_X)
        conf_anc, conf_cand = bootstrap_confusions(
            view.s_gate_y, [p_anc, p_cand], k, params.n_boot, rng)
        ds = stable_macro_f1_conf(conf_anc, stable) - stable_macro_f1_conf(conf_cand, stable)
        ds_ucb, ds_lcb = ucb(ds, a), lcb(ds, a)
        fpr_s = benign_fpr_conf(conf_cand, benign) - benign_fpr_conf(conf_anc, benign)
        fpr_s_ucb, fpr_s_lcb = ucb(fpr_s, a), lcb(fpr_s, a)
        ds_point = float(stable_macro_f1_conf(confusion(view.s_gate_y, p_anc, k), stable)
                         - stable_macro_f1_conf(confusion(view.s_gate_y, p_cand, k), stable))
        fpr_s_point = (_benign_fpr_point(view.s_gate_y, p_cand, k, benign)
                       - _benign_fpr_point(view.s_gate_y, p_anc, k, benign))

    statuses = {
        "utility": _utility_status(gain_point, gain_lcb),
        "stable_f1": _envelope_status(ds_lcb, ds_ucb, params.eps_s),
        "fpr_stable": _envelope_status(fpr_s_lcb, fpr_s_ucb, params.eps_fpr),
        "fpr_current": _envelope_status(fpr_cur_lcb, fpr_cur_ucb, params.eps_fpr),
    }
    failed = tuple(n for n, s in statuses.items() if s != "ok")
    return CandidateReport(
        True, "ok", gain_point, gain_lcb, ds_point, ds_ucb, fpr_s_point, fpr_s_ucb,
        fpr_cur_point, fpr_cur_ucb, statuses["utility"], statuses["stable_f1"],
        statuses["fpr_stable"], statuses["fpr_current"], failed, **support,
        delta_stable_f1_lcb=ds_lcb, delta_fpr_stable_lcb=fpr_s_lcb,
        delta_fpr_current_lcb=fpr_cur_lcb, **eps)


def _envelope_reason(report):
    statuses = report.envelope_statuses
    for label in ("violated", "unverifiable", "inconclusive"):   # known violation outranks
        if label in statuses:                                     # missing evidence
            return f"envelope_{label}"
    raise AssertionError("envelope reason requested for a passing envelope")


def promote(view: ControllerView, incumbent, candidate, region, params: InterventionParams,
            rng, anchor) -> Decision:
    require_view(view)
    if not region:
        return Decision(False, "no_affected_region", incumbent, None)
    report = evaluate_candidate(view, incumbent, candidate, region, params, rng, anchor)
    if not report.sanity_ok:
        return Decision(False, "sanity", incumbent, report)
    if not report.utility_ok:
        return Decision(False, f"utility_{report.utility_status}", incumbent, report)
    if not report.envelope_ok:
        return Decision(False, _envelope_reason(report), incumbent, report)
    return Decision(True, "promoted", candidate, report)
