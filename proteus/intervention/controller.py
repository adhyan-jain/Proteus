"""The sequential, utility-tested intervention controller (SPEC v1.4 section 3.1).

Per window the controller receives ONLY a `ControllerView` (plus the step index/seed through a
`DecisionContext`). The search below reads D_ref, D_real, D_sel and S_sel; it never reads D_gate or
S_gate (promotion's evidence; a test poisons them and checks that the step trace is unchanged) and has
no handle to E_t, S_report or any evaluation-side quantity.

    A  = affected region of the incumbent on D_sel                       (learner.compute_affected_region)
    th_R = fit(D_ref + D_real)                                          (always built first)
    I  = recall-deficient classes of th_R on D_sel with n_c >= n_min    (learner.compute_residual_sets)
    greedy dose search over an `Operator` (SMOTE / ROS / negative controls add synthetic rows;
    THRESH reweights th_R's scores). A step moves one class c in I_active one rung up:

        L_k(c)  = LCB_{alpha/K_max}( U_A(th_k^{+c}) - U_A(th_k) ; D_sel )       U_A = mean F1 over A
        safe    = UCB_{alpha/K_max}(stable macro-F1 drop on S_sel)           <= eps_S
                  UCB_{alpha/K_max}(benign-FPR rise on S_sel)                <= eps_FPR
                  UCB_{alpha/K_max}(benign-FPR rise on D_sel's benign rows)  <= eps_FPR
        (all three INCREMENTAL, against the current iterate th_k; the anchor-relative S_sel numbers are
        logged next to them. The final certification against the fixed anchor is the frozen gate in
        gate14.promote_star -- the step filter only has to keep the search path sane.)

    accept c* = argmax L over safe candidates with L > eta; classes that were unsafe or failed the
    test leave I_active. STOP: no admissible action | k = K_max | no safe candidate | best L <= eta.

The controller chooses class and dose only, never the operator (fixed per condition). Risk is a
constraint, never a trade-off weight.
"""
from proteus.config import DEFAULT_N_JOBS  # noqa: F401 -- first import: caps BLAS/OMP threads

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from proteus.intervention.generators import GeneratorError
from proteus.intervention.learner import (
    CandidateBuilder, TrainingAddition, compute_affected_region, compute_residual_sets,
    require_view)
from proteus.intervention.metrics import (
    benign_fpr_conf, bootstrap_confusions, confusion, lcb, region_utility_conf,
    stable_macro_f1_conf, ucb)

PURPOSE_REGION, PURPOSE_ELIGIBLE, PURPOSE_POOL, PURPOSE_STEP = 10, 11, 30, 31   # 12 = promotion (P0)
PURPOSE_PROMOTE_STAR, PURPOSE_PROMOTE_REAL, PURPOSE_CANARY = 32, 12, 33
WEIGHT_LADDER = (1.0, 2.0, 4.0, 8.0, 16.0)       # THRESH score multipliers; rung 0 = 1.0
STOP_REASONS = ("no_affected_region", "real_only_sufficient", "no_admissible", "k_max",
                "no_safe_candidate", "no_gain")


def sub_rng(ctx, purpose, *extra):
    """Deterministic stream derived from (seed, t, purpose, ...); never shared between purposes."""
    return np.random.default_rng([int(ctx.seed), int(ctx.t), int(purpose), *[int(e) for e in extra]])


# ----------------------------------------------------------------------------- operators
class ThreshModel:
    """th_R with class-score multipliers followed by argmax. No refit; multiplier 1 for every class
    is bit-identical to th_R's own predictions."""

    def __init__(self, base, weights):
        self.base = base
        self.weights = {int(c): float(w) for c, w in weights.items()}
        cls = np.asarray(base.classes_)
        self._w = np.array([self.weights.get(int(c), 1.0) for c in cls], dtype=float)
        self.n_features = base.n_features
        self.n_train_rows = base.n_train_rows

    @property
    def classes_(self):
        return self.base.classes_

    def predict_proba(self, X):
        p = np.asarray(self.base.predict_proba(X), dtype=float) * self._w
        return p / p.sum(axis=1, keepdims=True)

    def predict(self, X):
        return np.asarray(self.base.classes_)[self.predict_proba(X).argmax(axis=1)].astype(np.int64)


class DataOperator:
    """Adds synthetic (or duplicated) rows of class c to th_R's training set.

    prepare() fits one generator per class on that class's real fit rows only and draws ONE pool of
    min(floor(max(rho) * n_c), M_cap) rows with a (seed, t, purpose, c) stream; a dose is a PREFIX of
    that pool, so doses are nested and deterministic. D_syn lives only inside the operator: it is
    rebuilt every call, never enters D_real or any buffer, and is never persisted."""

    def __init__(self, name, make_generator):
        self.name = name
        self.make_generator = make_generator
        self.generators = {}

    def prepare(self, view, builder, theta_R, classes, params, ctx):
        self.view, self.builder, self.params = view, builder, params
        self.n_real = int(len(view.real_y))
        self.pools, self.n_c, self.fit_errors, self.generators = {}, {}, {}, {}
        for c in sorted(classes):
            Xc = view.real_X[view.real_y == c]
            self.n_c[c] = int(len(Xc))
            rng = sub_rng(ctx, PURPOSE_POOL, c)
            try:
                gen = self.make_generator(c, view, params)
                gen.fit(Xc, c, rng)
                m_max = min(int(np.floor(max(params.rho_ladder) * len(Xc))), params.m_cap)
                self.pools[c] = gen.sample(m_max, rng)
                self.generators[c] = gen
            except GeneratorError as e:
                self.pools[c] = np.empty((0, view.real_X.shape[1]), dtype=np.float32)
                self.fit_errors[c] = str(e)

    def m(self, c, rung):
        if rung <= 0 or c not in self.pools:
            return 0
        raw = int(np.floor(self.params.rho_ladder[rung] * self.n_c[c]))
        return min(raw, self.params.m_cap, len(self.pools[c]))

    def next_dose(self, c, doses):
        r = doses.get(c, 0)
        cur = self.m(c, r)
        for r2 in range(r + 1, len(self.params.rho_ladder)):
            if self.m(c, r2) > cur:
                return r2
        return None

    def n_syn(self, doses):
        return int(sum(self.m(c, r) for c, r in doses.items()))

    def feasible(self, doses):
        s = self.n_syn(doses)
        return s == 0 or s / (self.n_real + s) <= self.params.phi_max

    def build(self, doses):
        parts = [(self.pools[c][: self.m(c, r)], c) for c, r in sorted(doses.items())
                 if self.m(c, r) > 0]
        if not parts:
            return self.builder.build(self.view)
        X = np.vstack([p for p, _ in parts]).astype(np.float32, copy=False)
        y = np.concatenate([np.full(len(p), c, dtype=np.int64) for p, c in parts])
        return self.builder.build(self.view, TrainingAddition(X=X, y=y, source=self.name))

    def describe(self, doses):
        return {"n_syn": self.n_syn(doses),
                "phi": self.n_syn(doses) / max(1, self.n_real + self.n_syn(doses)),
                "per_class": {str(c): {"rung": int(r), "rho": float(self.params.rho_ladder[r]),
                                       "n_real": self.n_c.get(c, 0), "m": self.m(c, r)}
                              for c, r in sorted(doses.items())},
                "fit_errors": {str(c): e for c, e in self.fit_errors.items()},
                "mmd_p": {str(c): getattr(g, "last_p", None) for c, g in self.generators.items()
                          if getattr(g, "last_p", None) is not None}}


class ThresholdOperator:
    name = "THRESH"

    def prepare(self, view, builder, theta_R, classes, params, ctx):
        self.theta_R = theta_R
        self.fit_errors, self.generators = {}, {}

    def next_dose(self, c, doses):
        r = doses.get(c, 0)
        return r + 1 if r + 1 < len(WEIGHT_LADDER) else None

    def n_syn(self, doses):
        return 0

    def feasible(self, doses):
        return True

    def build(self, doses):
        return ThreshModel(self.theta_R, {c: WEIGHT_LADDER[r] for c, r in doses.items()})

    def describe(self, doses):
        return {"n_syn": 0, "phi": 0.0,
                "per_class": {str(c): {"rung": int(r), "weight": float(WEIGHT_LADDER[r])}
                              for c, r in sorted(doses.items())}, "fit_errors": {}, "mmd_p": {}}


# ----------------------------------------------------------------------------- controller
@dataclass(frozen=True)
class ControllerOptions:
    """Switches for the preregistered ablations (SPEC v1.4); the defaults are the method."""
    step_test: bool = True        # False: rank by POINT gain, accept any positive point gain
    step_safety: bool = True      # False: no incremental envelope filter during the search
    need_test: bool = True        # False: I := A (restricted to n_c >= n_min)
    k_cap: Optional[int] = None   # overrides K_max (the K_max = 1 ablation)


@dataclass(frozen=True)
class ControllerRun:
    region: tuple
    eligible: tuple
    theta_R: Any
    theta_star: Any               # th_R if k == 0; None only when the region is empty
    k: int
    doses: dict
    stop_reason: str
    steps: list                   # JSON-safe iteration traces
    candidate_fits: int
    operator_info: dict
    region_info: dict = field(default_factory=dict)


class InterventionController:
    def __init__(self, operator, options: ControllerOptions = ControllerOptions()):
        self.operator = operator
        self.options = options

    # -- the whole per-window procedure -------------------------------------------------------
    def run(self, view, incumbent, ctx, anchor=None) -> ControllerRun:
        require_view(view)
        params = ctx.params
        info = compute_affected_region(view, incumbent, params, ctx.rng(PURPOSE_REGION))
        trace = {"measurable": list(info.measurable), "region": list(info.region),
                 "deficiency_lcb": {str(c): v for c, v in info.deficiency_lcb.items()}}
        if not info.region:
            return ControllerRun((), (), None, None, 0, {}, "no_affected_region", [], 0, {}, trace)

        builder = CandidateBuilder(params, ctx.seed)
        theta_R = builder.build(view)
        residual = compute_residual_sets(view, theta_R, info.region, params,
                                         ctx.rng(PURPOSE_ELIGIBLE))
        trace.update({"eligible_recall": list(residual.eligible),
                      "eligible_f1_diagnostic": list(residual.f1_diagnostic)})
        n_c = np.bincount(view.real_y, minlength=len(view.class_names))
        if self.options.need_test:
            eligible = tuple(residual.eligible)
        else:
            eligible = tuple(c for c in info.region if n_c[c] >= params.n_min)
        if not eligible:
            return ControllerRun(info.region, (), theta_R, theta_R, 0, {}, "real_only_sufficient",
                                 [], 0, {}, trace)
        return self._search(view, ctx, anchor, info.region, eligible, theta_R, builder, trace)

    # -- greedy dose search -------------------------------------------------------------------
    def _search(self, view, ctx, anchor, region, eligible, theta_R, builder, region_info):
        params, opt, op = ctx.params, self.options, self.operator
        op.prepare(view, builder, theta_R, eligible, params, ctx)
        k_cls = len(view.class_names)
        benign = list(view.class_names).index(params.benign_label)
        s_support = np.bincount(view.s_sel_y, minlength=k_cls)
        stable = [int(c) for c in np.unique(view.ref_y) if s_support[c] >= params.s_min]
        a_step = params.step_alpha
        k_max = params.k_max if opt.k_cap is None else min(params.k_max, opt.k_cap)

        cur, doses, active = theta_R, {}, set(eligible)
        p_cur_sel, p_cur_s = cur.predict(view.sel_X), cur.predict(view.s_sel_X)
        p_anchor_s = anchor.predict(view.s_sel_X) if anchor is not None else None
        steps, fits, stop, k = [], 0, None, 0
        while True:
            if k >= k_max:
                stop = "k_max"
                break
            cands = []
            for c in sorted(active):
                nxt = op.next_dose(c, doses)
                if nxt is None or not op.feasible({**doses, c: nxt}):
                    active.discard(c)
                    continue
                cands.append((c, nxt, {**doses, c: nxt}))
            if not cands:
                stop = "no_admissible"
                break

            models = [op.build(nd) for _, _, nd in cands]
            fits += len(models)
            p_sel = [m.predict(view.sel_X) for m in models]
            p_s = [m.predict(view.s_sel_X) for m in models]
            rng = sub_rng(ctx, PURPOSE_STEP, k)
            confs_sel = bootstrap_confusions(view.sel_y, [p_cur_sel, *p_sel], k_cls,
                                             params.n_boot, rng)
            confs_s = None
            if len(view.s_sel_y) and stable:
                extra = [p_anchor_s] if p_anchor_s is not None else []
                confs_s = bootstrap_confusions(view.s_sel_y, [p_cur_s, *p_s, *extra], k_cls,
                                               params.n_boot, rng)
            rec_c = []
            for i, (c, nxt, nd) in enumerate(cands):
                gain = region_utility_conf(confs_sel[i + 1], region) \
                    - region_utility_conf(confs_sel[0], region)
                point = float(region_utility_conf(confusion(view.sel_y, p_sel[i], k_cls), region)
                              - region_utility_conf(confusion(view.sel_y, p_cur_sel, k_cls), region))
                d_fpr_sel = benign_fpr_conf(confs_sel[i + 1], benign) \
                    - benign_fpr_conf(confs_sel[0], benign)
                d_stable = d_fpr_s = anc_stable = anc_fpr = float("nan")
                if confs_s is not None:
                    d_stable = ucb(stable_macro_f1_conf(confs_s[0], stable)
                                   - stable_macro_f1_conf(confs_s[i + 1], stable), a_step)
                    d_fpr_s = ucb(benign_fpr_conf(confs_s[i + 1], benign)
                                  - benign_fpr_conf(confs_s[0], benign), a_step)
                    if p_anchor_s is not None:
                        anc_stable = ucb(stable_macro_f1_conf(confs_s[-1], stable)
                                         - stable_macro_f1_conf(confs_s[i + 1], stable), a_step)
                        anc_fpr = ucb(benign_fpr_conf(confs_s[i + 1], benign)
                                      - benign_fpr_conf(confs_s[-1], benign), a_step)
                d_fpr_sel_ucb = ucb(d_fpr_sel, a_step)
                ok = bool(np.isfinite([d_stable, d_fpr_s, d_fpr_sel_ucb]).all()
                          and d_stable <= params.eps_s and d_fpr_s <= params.eps_fpr
                          and d_fpr_sel_ucb <= params.eps_fpr)
                rec_c.append({
                    "c": int(c), "rung": int(nxt), "n_syn_after": op.n_syn(nd),
                    "gain_lcb": lcb(gain, a_step), "gain_point": point,
                    "d_fpr_sel_ucb": d_fpr_sel_ucb, "d_stable_s_ucb": d_stable,
                    "d_fpr_s_ucb": d_fpr_s, "anchor_d_stable_s_ucb": anc_stable,
                    "anchor_d_fpr_s_ucb": anc_fpr,
                    "safe": True if not opt.step_safety else ok, "safe_strict": ok})

            safe = [i for i, r in enumerate(rec_c) if r["safe"]]
            score = (lambda r: r["gain_lcb"]) if opt.step_test else (lambda r: r["gain_point"])
            floor = params.eta if opt.step_test else 0.0
            passing = [i for i in safe if np.isfinite(score(rec_c[i])) and score(rec_c[i]) > floor]
            entry = {"k": k, "active": sorted(int(c) for c in active), "candidates": rec_c,
                     "accepted": None}
            steps.append(entry)
            if not safe:
                stop = "no_safe_candidate"
                break
            if not passing:
                stop = "no_gain"
                break
            best = max(passing, key=lambda i: (score(rec_c[i]), -cands[i][0]))
            c, nxt, nd = cands[best]
            entry["accepted"] = int(c)
            doses, cur = nd, models[best]
            p_cur_sel, p_cur_s = p_sel[best], p_s[best]
            active = {cands[i][0] for i in passing}        # unsafe / failed classes leave I_active
            k += 1

        return ControllerRun(region, tuple(eligible), theta_R, cur, k, dict(doses), stop, steps,
                             fits, op.describe(doses), region_info)
