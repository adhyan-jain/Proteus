"""Candidate construction and drift-region analysis (SPEC v1.0, sections 1.4 and 2).

Everything here consumes a `ControllerView` and nothing else. The view is the single source of
data: this module has no import of, and no code path to, the dataset bundle, the partition
manifest, the replay objects, the reporting rows, the unlabelled rows, the drift-detector
reference or future windows. (A static test enforces that.)

`TrainingAddition` is the one plug-in point for later intervention operators: a candidate is
always `fit(ref + real [+ addition])`. The evaluation protocol never changes when an operator is
added; only what gets passed as `extra` does.
"""
from proteus.config import DEFAULT_N_JOBS  # first import: caps BLAS/OMP threads before numpy/sklearn

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from proteus.intervention.metrics import (
    bootstrap_confusions, f1_from_conf, lcb, recall_from_conf)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import ControllerView


def require_view(view):
    if not isinstance(view, ControllerView):
        raise TypeError(f"expected a ControllerView, got {type(view).__name__}: the learner and "
                        f"promotion code may only consume data exposed through the view")


@dataclass(frozen=True)
class RFModel:
    clf: RandomForestClassifier
    n_features: int
    n_train_rows: int

    @property
    def classes_(self):
        return self.clf.classes_

    def predict(self, X):
        return np.asarray(self.clf.predict(X), dtype=np.int64)

    def predict_proba(self, X):
        return self.clf.predict_proba(X)


@dataclass(frozen=True)
class TrainingAddition:
    """Extra labelled rows appended to a candidate's training set by an intervention operator."""
    X: np.ndarray
    y: np.ndarray
    source: str

    def __post_init__(self):
        if self.X.ndim != 2 or len(self.X) != len(self.y):
            raise ValueError("TrainingAddition needs X of shape (n, d) and y of length n")


def _fit_rf(X, y, params, seed):
    clf = RandomForestClassifier(n_estimators=params.rf_n_estimators,
                                 max_depth=params.rf_max_depth, random_state=seed,
                                 n_jobs=DEFAULT_N_JOBS)
    clf.fit(X, y)
    return RFModel(clf=clf, n_features=int(X.shape[1]), n_train_rows=int(len(X)))


class CandidateBuilder:
    """Pure: builds a fresh model from the view; never mutates the incumbent or the view."""

    def __init__(self, params: InterventionParams, seed: int):
        self.params = params
        self.seed = seed

    def build_base(self, view: ControllerView) -> RFModel:
        """theta_0 = theta_base := fit(D_ref) (SPEC v1.1, D1). The only data it can touch is the
        view's reference reservoir, with the same learner and seed as every candidate, so every
        later candidate fit(D_ref + D_real [+ D_syn]) is a strict superset of its training set."""
        require_view(view)
        model = _fit_rf(view.ref_X.astype(np.float32, copy=False),
                        view.ref_y.astype(np.int64, copy=False), self.params, self.seed)
        assert model.n_train_rows == len(view.ref_X), "base model must train on exactly D_ref"
        return model

    def build(self, view: ControllerView, extra: Optional[TrainingAddition] = None) -> RFModel:
        require_view(view)
        Xs, ys = [view.ref_X, view.real_X], [view.ref_y, view.real_y]
        if extra is not None:
            if extra.X.shape[1] != view.ref_X.shape[1]:
                raise ValueError("TrainingAddition feature width differs from the view's")
            Xs.append(extra.X)
            ys.append(extra.y)
        X = np.vstack(Xs).astype(np.float32, copy=False)
        y = np.concatenate(ys).astype(np.int64, copy=False)
        return _fit_rf(X, y, self.params, self.seed)


@dataclass(frozen=True)
class RegionInfo:
    measurable: tuple             # M: support >= s_min in both D_sel and D_gate
    region: tuple                 # A: measurable and LCB_alpha(deficiency of incumbent) > eps_def
    deficiency_lcb: dict          # class -> LCB_alpha(d_c(incumbent)) for classes in M


def measurable_classes(view: ControllerView, params: InterventionParams):
    k = len(view.class_names)
    sel = np.bincount(view.sel_y, minlength=k)
    gate = np.bincount(view.gate_y, minlength=k)
    return tuple(int(c) for c in np.flatnonzero((sel >= params.s_min) & (gate >= params.s_min)))


def _deficiency_lcb(view, model, classes, params, rng):
    k = len(view.class_names)
    (conf,) = bootstrap_confusions(view.sel_y, [model.predict(view.sel_X)], k, params.n_boot,
                                   rng)
    d = 1.0 - f1_from_conf(conf)                       # (R, K)
    return {int(c): lcb(d[:, c], params.alpha) for c in classes}


def compute_affected_region(view: ControllerView, incumbent, params: InterventionParams,
                            rng) -> RegionInfo:
    """A = {c in M : LCB_alpha(1 - F1_c(incumbent; D_sel)) > eps_def}. Empty if nothing is
    measurable (the run then does nothing)."""
    require_view(view)
    m = measurable_classes(view, params)
    if not m:
        return RegionInfo(measurable=(), region=(), deficiency_lcb={})
    d_lcb = _deficiency_lcb(view, incumbent, m, params, rng)
    region = tuple(c for c in m if d_lcb[c] > params.eps_def)
    return RegionInfo(measurable=m, region=region, deficiency_lcb=d_lcb)


@dataclass(frozen=True)
class ResidualSets:
    eligible: tuple             # I (v1.1, D4): recall deficiency -- the set P0 and the controller use
    f1_diagnostic: tuple        # same rule with F1 deficiency; logged only, never used to decide


def compute_residual_sets(view: ControllerView, candidate, region, params: InterventionParams,
                          rng) -> ResidualSets:
    """Residual deficiency after real-only adaptation, on D_sel (SPEC v1.1, D4).

      I = {c in A : LCB_alpha(1 - Recall_c(candidate; D_sel)) > eps_def and n_c >= n_min}

    n_c counts real fit rows of class c in the view. Recall, not F1: adding rows of class c can
    only repair c's recall, not other classes' leakage into c (which lowers c's precision). The
    F1-based version of the same rule is returned as `f1_diagnostic` for logging. Both sets come
    from one bootstrap, so they are directly comparable. Does not gate any decision."""
    require_view(view)
    if not region:
        return ResidualSets((), ())
    k = len(view.class_names)
    (conf,) = bootstrap_confusions(view.sel_y, [candidate.predict(view.sel_X)], k,
                                   params.n_boot, rng)
    d_recall = 1.0 - recall_from_conf(conf)
    d_f1 = 1.0 - f1_from_conf(conf)
    n_c = np.bincount(view.real_y, minlength=k)

    def pick(d):
        return tuple(c for c in region
                     if lcb(d[:, c], params.alpha) > params.eps_def and n_c[c] >= params.n_min)

    return ResidualSets(eligible=pick(d_recall), f1_diagnostic=pick(d_f1))
