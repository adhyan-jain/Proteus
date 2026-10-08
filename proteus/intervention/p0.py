"""P0 runner: replay FROZEN, REAL_ONLY and REAL_ONLY_ALL_LABELS under the oracle trigger (SPEC v1.1).

    python -m proteus.intervention.p0 --scenario S1 --budgets 25 100 --seeds 0 1 2 3 4

One manifest per (seed, budget) is built once and shared by every condition, as are the base model
theta_base = fit(D_ref), the seeds and the partitions. The conditions differ ONLY in the label regime
(FROZEN and REAL_ONLY see the B labels of L_t, the positive control sees every non-E row; all with the
same one-window delay) and in what they do with the view.

Per window t (SPEC section 1.3, prequential):
  1. the deployed model predicts W_t; E_t is scored by the runner (evaluation side, never fed back);
  2. the labels of window t-1 arrive (`StreamStep.arrived_idx`) and the buffers are updated;
  3. the V1 audit checks the provenance of every array in the view;
  4. post-drift windows only (oracle trigger: the episode is active for every post-drift window):
     `condition.decide(view, incumbent, ctx)`; the chosen model is deployed from t+1.
The controller side receives a `ControllerView` and a `DecisionContext` (step, seed, frozen params and
the theta_base model) -- nothing else. FROZEN is diagnosed by the runner (`compute_affected_region`
on the same view, against theta_base) so that V2/V3 exist without FROZEN ever reading the view.

Result files (strict JSON, see serialize.py), written in this key order so validity precedes H1:
  header/provenance -> manifests -> validity (V1-V4) -> h1 -> runs -> aggregate -> timings.
H1 is only assigned when every validity check passed and the configuration is the preregistered one.
"""
import proteus.config  # noqa: F401 -- must import before numpy/pandas/sklearn to cap BLAS/OMP threads

import argparse
import hashlib
import logging
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from proteus.intervention.cache import (
    CACHE_PATH, MemoryBlocker, cache_status, load_cache, load_provenance, require_memory)
from proteus.intervention.conditions import (
    LABEL_REGIME_ALL_NON_E, LABEL_REGIME_BUDGET, DecisionContext, Frozen, RealOnly,
    RealOnlyAllLabels)
from proteus.intervention.diagnostics import (
    ambiguity_shares, ambiguous_groups, contamination_counts, label_conflict_report)
from proteus.intervention.learner import CandidateBuilder, compute_affected_region
from proteus.intervention.metrics import (
    benign_fpr_conf, confusion, f1_from_conf, stable_macro_f1_conf, t_ci)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import (
    ROLE_FIT, ROLE_GATE, ROLE_SEL, SCENARIOS, SPEC_VERSION, StreamReplay, StreamState, StreamStep,
    _role_of_groups, build_partitions)
from proteus.intervention.provenance import git_state, library_versions, utc_now_iso
from proteus.intervention.serialize import write_json
from proteus.intervention.validity import P0Criteria, evaluate_p0, spec_rules_sha256

log = logging.getLogger("proteus.intervention.p0")

CONDITION_NAMES = ("FROZEN", "REAL_ONLY", "REAL_ONLY_ALL_LABELS")
_PURPOSE_FROZEN_DIAGNOSTIC = 20            # rng stream for the runner's FROZEN region diagnostic
_NAN = float("nan")


def make_conditions():
    return [Frozen(), RealOnly(), RealOnlyAllLabels()]


def _cat(parts):
    parts = [np.asarray(p, dtype=np.int64) for p in parts]
    return np.concatenate(parts) if parts else np.empty(0, dtype=np.int64)


# ------------------------------------------------------------------------------- label regimes
def all_labels_steps(data, manifest):
    """Positive-control stream: same windows, same delay, same roles by group hash, but every non-E
    row of window t-1 (L_{t-1} then U_{t-1}) arrives at t. E_t is never included, so the budget
    regime's labelled rows are a strict prefix-subset of this regime's, on the same manifest."""
    prev_idx = prev_role = np.empty(0, dtype=np.int64)
    for spec in manifest.windows:
        yield StreamStep(t=spec.t, phase=spec.phase, spec=spec, arrived_idx=prev_idx,
                         arrived_role=prev_role)
        prev_idx = _cat([spec.l_idx, spec.u_idx])
        prev_role = _cat([spec.l_role, _role_of_groups(data.group[spec.u_idx], manifest.seed)])


def replay_steps(data, manifest, regime):
    if regime == LABEL_REGIME_BUDGET:
        return iter(StreamReplay(manifest))
    if regime == LABEL_REGIME_ALL_NON_E:
        return all_labels_steps(data, manifest)
    raise ValueError(f"unknown label regime {regime!r}")


class TrackedState(StreamState):
    """StreamState that counts how many rows each FIFO buffer evicted (the positive control
    overflows the 5000-row real buffer; the result file must say so)."""

    def __init__(self, data, manifest):
        super().__init__(data, manifest)
        self.evicted = {"real": 0, "sel": 0, "gate": 0}
        self.ingested = {"real": 0, "sel": 0, "gate": 0}

    def ingest(self, step):
        before = {"real": len(self._real), "sel": len(self._sel), "gate": len(self._gate)}
        super().ingest(step)
        roles = np.asarray(step.arrived_role)
        for name, role in (("real", ROLE_FIT), ("sel", ROLE_SEL), ("gate", ROLE_GATE)):
            n_in = int((roles == role).sum())
            after = len(getattr(self, "_" + name))
            self.ingested[name] += n_in
            self.evicted[name] += before[name] + n_in - after

    def buffer_sizes(self):
        return {"real": len(self._real), "sel": len(self._sel), "gate": len(self._gate)}


# ------------------------------------------------------------------------------------ V1 audit
class Auditor:
    """Re-audits the manifest and, at every step, the provenance of every array in the view."""

    def __init__(self, data, manifest, ambiguous=None):
        self.group = data.group
        self.y = data.y
        self.m = manifest
        cfg = manifest.config
        # groups carrying more than one label anywhere in the corpus (diagnostic only); pass it in
        # to avoid recomputing over the whole corpus for every manifest
        self.ambiguous = (ambiguous_groups(data.group, data.y) if ambiguous is None
                          else ambiguous)
        self.pool = np.zeros(len(data.day), dtype=np.int8)
        self.pool[np.isin(data.day, cfg.pre_days)] = 1
        self.pool[np.isin(data.day, cfg.drift_days)] = 2
        parts = manifest.partition_rows()
        self.dest_groups = {"S_report": np.unique(self.group[parts["s_report"]]),
                            "S_gate": np.unique(self.group[parts["s_gate"]]),
                            "S_sel": np.unique(self.group[parts["s_sel"]]),
                            "S_cal": np.unique(self.group[parts["s_cal"]]),
                            "D_ref": np.unique(self.group[parts["ref"]])}
        w = manifest.windows
        self.e_rows = _cat([x.e_idx for x in w])
        self.u_rows = _cat([x.u_idx for x in w])
        self.forbidden = _cat([self.e_rows, manifest.s_report_idx, manifest.s_cal_idx])
        self.forb_groups = {p: np.unique(self.group[self.forbidden[self.pool[self.forbidden] == p]])
                            for p in (1, 2)}
        self.l_by_t = {x.t: np.asarray(x.l_idx, dtype=np.int64) for x in w}
        self.all_by_t = {x.t: _cat([x.l_idx, x.u_idx]) for x in w}

    def audit_view(self, prov, t, regime):
        out = {"n_row_overlap": 0, "n_same_pool_group_overlaps": 0,
               "n_cross_pool_group_overlaps": 0, "n_unlabelled_rows": 0, "n_future_rows": 0}
        learned = ("real", "sel", "gate")
        by_t = self.l_by_t if regime == LABEL_REGIME_BUDGET else self.all_by_t
        allowed = _cat([rows for w, rows in by_t.items() if w < t])
        for name, rows in prov.items():
            rows = np.asarray(rows, dtype=np.int64)
            if not len(rows):
                continue
            out["n_row_overlap"] += int(np.isin(rows, self.forbidden).sum())
            for p in (1, 2):
                g = self.group[rows[self.pool[rows] == p]]
                out["n_same_pool_group_overlaps"] += int(np.isin(g, self.forb_groups[p]).sum())
                out["n_cross_pool_group_overlaps"] += int(np.isin(g, self.forb_groups[3 - p]).sum())
            if regime == LABEL_REGIME_BUDGET:
                out["n_unlabelled_rows"] += int(np.isin(rows, self.u_rows).sum())
            if name in learned:
                out["n_future_rows"] += int((~np.isin(rows, allowed)).sum())
        out["n_violations"] = (out["n_row_overlap"] + out["n_same_pool_group_overlaps"]
                               + out["n_unlabelled_rows"] + out["n_future_rows"])
        return out

    def contamination(self, prov):
        """Diagnostic (never gates): learning-buffer rows duplicated in stable-evaluation sets."""
        return contamination_counts(prov, self.pool, self.group, self.dest_groups)

    def ambiguity(self, prov, drift_classes):
        """Diagnostic (never gates): share of drift-class rows whose feature vector carries
        another label, over the final D_sel and over the pooled post-drift E rows."""
        cfg = self.m.config
        e_rows = _cat([w.e_idx for w in self.m.windows if w.t > cfg.n_pre_windows])
        return {"d_sel": ambiguity_shares(prov["sel"], self.group, self.y, self.ambiguous,
                                          drift_classes),
                "e_pooled": ambiguity_shares(e_rows, self.group, self.y, self.ambiguous,
                                             drift_classes)}

    def audit_manifest(self):
        m = self.m
        pre_w = [x for x in m.windows if x.phase == "pre"]
        drift_w = [x for x in m.windows if x.phase == "post"]

        def g(idx):
            return np.unique(self.group[_cat([idx])])

        parts = m.partition_rows()
        pre = {name: g(parts[name]) for name in ("train", "s_cal", "s_sel", "s_gate", "s_report")}
        pre |= {"pre_e": g(_cat([x.e_idx for x in pre_w])),
               "pre_learn": g(_cat([x.l_idx for x in pre_w] + [x.u_idx for x in pre_w]))}
        drift = {"drift_e": g(_cat([x.e_idx for x in drift_w])),
                 "drift_learn": g(_cat([x.l_idx for x in drift_w] + [x.u_idx for x in drift_w]))}
        overlaps, same = {}, 0
        for sets in (pre, drift):
            names = list(sets)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    n = int(np.intersect1d(sets[a], sets[b], assume_unique=True).size)
                    if n:
                        overlaps[f"{a}&{b}"] = n
                        same += n
        ref_not_in_train = int(np.setdiff1d(parts["ref"], parts["train"]).size)
        window_rows = _cat([self.e_rows, self.u_rows, _cat([x.l_idx for x in m.windows])])
        row_reuse = int(len(window_rows) - len(np.unique(window_rows)))
        cross = int(np.intersect1d(np.unique(np.concatenate(list(pre.values()))),
                                   np.unique(np.concatenate(list(drift.values()))),
                                   assume_unique=True).size)
        return {"n_same_pool_group_overlaps": same + ref_not_in_train + row_reuse,
                "n_cross_pool_group_overlaps": cross, "overlapping_pairs": overlaps,
                "n_ref_rows_not_in_train": ref_not_in_train, "n_window_row_reuse": row_reuse}


# ------------------------------------------------------------------------------------- scoring
def _cells(conf):
    return [[int(i), int(j), int(conf[i, j])] for i, j in np.argwhere(conf > 0)]


def _conf_from_cells(cells, k):
    conf = np.zeros((k, k), dtype=np.int64)
    for i, j, n in cells:
        conf[i, j] = n
    return conf


def s_report_stats(model, data, manifest, stable, benign, k, s_min):
    """Evaluation-side stable-traffic score on S_report (never visible to the controller)."""
    idx = manifest.s_report_idx
    conf = confusion(data.y[idx], model.predict(data.X[idx]), k)
    present = [c for c in stable if conf[c].sum() >= s_min]
    return {"stable_macro_f1": float(stable_macro_f1_conf(conf, present)) if present else _NAN,
            "benign_fpr": float(benign_fpr_conf(conf, benign)),
            "n_stable_classes": len(present), "n_rows": int(len(idx))}


def drift_classes_of(data, cfg):
    """Classes with rows in the drift pool and none in the pre-drift pool."""
    pre = set(np.unique(data.y[np.isin(data.day, cfg.pre_days)]).tolist())
    drift = set(np.unique(data.y[np.isin(data.day, cfg.drift_days)]).tolist())
    return sorted(int(c) for c in drift - pre)


def recovery_from_steps(rec, s_min, k):
    """Primary endpoint (SPEC section 4): mean over post-drift windows after t_d of region F1 on
    E_t. The region is fixed after the fact: drift classes with pooled E support >= s_min. Windows
    where no region class has E support are skipped (NaN)."""
    post = [s for s in rec["steps"] if s["t"] > rec["n_pre_windows"]]
    confs = [_conf_from_cells(s["e_conf_cells"], k) for s in post]
    if not confs:
        return {"region": [], "auc": _NAN, "per_window_region_f1": [], "n_windows_scored": 0}
    support = np.sum(confs, axis=0).sum(axis=1)
    region = [c for c in rec["drift_classes"] if support[c] >= s_min]
    per_window = []
    for conf in confs:
        cls = [c for c in region if conf[c].sum() > 0]
        per_window.append(float(f1_from_conf(conf)[cls].mean()) if cls else _NAN)
    finite = [v for v in per_window if v == v]
    return {"region": region, "auc": float(np.mean(finite)) if finite else _NAN,
            "per_window_region_f1": per_window, "n_windows_scored": len(finite)}


def _stable_effect(rec, base_stats):
    after = [s["s_report"] for s in rec["steps"] if s.get("s_report")]
    final = after[-1] if after else None
    drops = [base_stats["stable_macro_f1"] - a["stable_macro_f1"] for a in after]
    incs = [a["benign_fpr"] - base_stats["benign_fpr"] for a in after]
    return {"base": base_stats, "final": final,
            "final_stable_macro_f1_drop": drops[-1] if drops else _NAN,
            "final_benign_fpr_increase": incs[-1] if incs else _NAN,
            "worst_stable_macro_f1_drop": max(drops, default=_NAN),
            "worst_benign_fpr_increase": max(incs, default=_NAN)}


def _summarize(rec, base_stats, class_names, params):
    k = len(class_names)
    post = [s for s in rec["steps"] if s["t"] > rec["n_pre_windows"]]
    active = [s for s in rec["steps"] if s["controller_active"] and rec["condition"] != "FROZEN"]
    meas, reg = Counter(), Counter()
    for s in post:
        for c in s["measurable"]:
            meas[class_names[c]] += 1
        for c in s["region"]:
            reg[class_names[c]] += 1
    reports = [s["decision"]["report"] for s in active if s.get("decision")
               and s["decision"].get("report")]
    support = {key: [r[key] for r in reports]
               for key in ("n_gate_rows", "n_gate_region_rows", "n_gate_benign", "n_s_gate_rows",
                           "n_s_gate_benign", "n_stable_classes")}
    return {
        "recovery": recovery_from_steps(rec, params.s_min, k),
        "stable_reference_effect": _stable_effect(rec, base_stats),
        "reason_counts": dict(Counter(s["reason"] for s in active)),
        "n_promotions": sum(bool(s["promoted"]) for s in active),
        "n_post_windows": len(post),
        "measurable_windows_by_class": dict(meas),
        "region_windows_by_class": dict(reg),
        "support_counts_per_decision": support,
    }


# ------------------------------------------------------------------------------------ replay
def run_condition(data, manifest, condition, params, base, base_stats, aud, drift_classes):
    """Replay one condition on one manifest. Returns the run record."""
    seed, cfg = manifest.seed, manifest.config
    regime = condition.label_regime
    k = len(data.class_names)
    benign = list(data.class_names).index(params.benign_label)
    stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
    state = TrackedState(data, manifest)
    stream = hashlib.sha256()
    incumbent, incumbent_stats = base, base_stats
    steps, v1 = [], Counter()
    t_start = time.perf_counter()

    for step in replay_steps(data, manifest, regime):
        t0 = time.perf_counter()
        e_idx = step.spec.e_idx                                  # evaluation side only
        e_conf = confusion(data.y[e_idx], incumbent.predict(data.X[e_idx]), k)

        state.ingest(step)
        stream.update(f"{step.t}:".encode() + np.ascontiguousarray(
            step.arrived_idx, dtype=np.int64).tobytes())
        view = state.view()
        audit = aud.audit_view(state.provenance(), step.t, regime)
        v1.update(audit)

        rec = {"t": step.t, "phase": step.phase, "controller_active": step.phase == "post",
               "n_arrived_labels": int(len(step.arrived_idx)),
               "buffer_sizes": state.buffer_sizes(), "evicted_rows": dict(state.evicted),
               "real_class_counts": np.bincount(view.real_y, minlength=k).tolist(),
               "region": [], "measurable": [], "eligible": None, "eligible_f1_diagnostic": None,
               "promoted": None, "reason": None, "n_train_rows": None, "decision": None,
               "e_n": int(len(e_idx)), "e_conf_cells": _cells(e_conf), "v1_audit": audit}
        t_decide = 0.0
        ctx = DecisionContext(t=step.t, seed=seed, params=params, anchor=base)
        if isinstance(condition, Frozen):
            info = compute_affected_region(view, incumbent, params,
                                           ctx.rng(_PURPOSE_FROZEN_DIAGNOSTIC))
            rec.update(region=list(info.region), measurable=list(info.measurable))
        if rec["controller_active"]:
            t1 = time.perf_counter()
            out = condition.decide(view, incumbent, ctx)
            t_decide = time.perf_counter() - t1
            trace = out.trace
            rec.update(promoted=bool(out.promoted), reason=out.reason,
                       region=list(out.region) or rec["region"],
                       measurable=trace.get("measurable", rec["measurable"]),
                       eligible=trace.get("eligible"),
                       eligible_f1_diagnostic=trace.get("eligible_f1_diagnostic"),
                       n_train_rows=trace.get("n_train_rows"), decision=trace.get("decision"))
            if out.model is not incumbent:
                incumbent = out.model
                incumbent_stats = s_report_stats(incumbent, data, manifest, stable, benign, k,
                                                 params.s_min)
        rec["deployed_is_base"] = incumbent is base
        rec["s_report"] = incumbent_stats
        rec["timings"] = {"decide_s": round(t_decide, 3),
                          "step_s": round(time.perf_counter() - t0, 3)}
        steps.append(rec)

    record = {
        "kind": "p0_run", "condition": condition.name, "label_regime": regime,
        "is_positive_control": bool(getattr(condition, "is_positive_control", False)),
        "seed": seed, "budget": cfg.budget, "scenario": cfg.name,
        "n_pre_windows": cfg.n_pre_windows, "n_post_windows": cfg.n_post_windows,
        "window_size": cfg.window_size, "drift_classes": drift_classes,
        "manifest_digest": manifest.digest(), "label_stream_digest": stream.hexdigest(),
        "buffer": {"real_buffer_cap": cfg.real_buffer_cap, "eval_buffer_cap": cfg.eval_buffer_cap,
                   "ingested_rows": dict(state.ingested), "evicted_rows": dict(state.evicted),
                   "final_sizes": state.buffer_sizes(),
                   "real_buffer_evicted": state.evicted["real"] > 0,
                   "note": "FIFO caps drop the oldest rows; evictions mean the nesting "
                           "D_ref < D_real < candidate holds for current buffer contents only."},
        "v1": {"n_violations": int(v1["n_violations"]),
               "n_row_overlap": int(v1["n_row_overlap"]),
               "n_same_pool_group_overlaps": int(v1["n_same_pool_group_overlaps"]),
               "n_cross_pool_group_overlaps": int(v1["n_cross_pool_group_overlaps"]),
               "n_unlabelled_rows": int(v1["n_unlabelled_rows"]),
               "n_future_rows": int(v1["n_future_rows"]), "n_steps_audited": len(steps)},
        "steps": steps,
        "timings": {"total_s": round(time.perf_counter() - t_start, 2)},
    }
    final_prov = state.provenance()
    record["ambiguity"] = aud.ambiguity(final_prov, drift_classes)
    record["contamination"] = aud.contamination(final_prov)
    record["summary"] = _summarize(record, base_stats, list(data.class_names), params)
    return record


# ------------------------------------------------------------------------------- orchestration
def check_preregistered(scenario_cfg, budgets, seeds, params, criteria):
    problems = []
    registered = SCENARIOS.get(criteria.scenario)
    if registered is None or replace(scenario_cfg, budget=0) != replace(registered, budget=0):
        problems.append("scenario configuration differs from the preregistered S1 configuration")
    if tuple(budgets) != tuple(criteria.budgets):
        problems.append(f"budgets {tuple(budgets)} != preregistered {tuple(criteria.budgets)}")
    if tuple(seeds) != tuple(criteria.seeds):
        problems.append(f"seeds {tuple(seeds)} != preregistered {tuple(criteria.seeds)}")
    if params.digest() != InterventionParams().digest():
        problems.append("parameters differ from the frozen section 1.5 defaults")
    return not problems, problems


def audit_budget_nesting(small, large):
    """Spec L.1 scope: budgets are nested on a matched seed. Partitions and E_t are identical, the
    labelled rows of the smaller budget are a prefix of the larger one's (same roles), and the
    larger budget's unlabelled rows are the smaller one's minus the extra labelled rows."""
    problems = []
    if small.seed != large.seed:
        problems.append("different seeds")
    ps, pl = small.partition_rows(), large.partition_rows()
    problems += [f"partition {k} differs" for k in ps if not np.array_equal(ps[k], pl[k])]
    if len(small.windows) != len(large.windows):
        problems.append("different window counts")
    else:
        bs, bl = small.config.budget, large.config.budget
        for ws, wl in zip(small.windows, large.windows):
            if not np.array_equal(ws.e_idx, wl.e_idx):
                problems.append(f"t={ws.t}: E_t differs")
            if not np.array_equal(ws.l_idx, wl.l_idx[:bs]):
                problems.append(f"t={ws.t}: labelled rows are not a prefix")
            if not np.array_equal(ws.l_role, wl.l_role[:bs]):
                problems.append(f"t={ws.t}: roles differ on the shared labelled rows")
            if not np.array_equal(ws.u_idx[bl - bs:], wl.u_idx):
                problems.append(f"t={ws.t}: unlabelled rows are not the remainder")
    return {"seed": small.seed, "budgets": [small.config.budget, large.config.budget],
            "n_violations": len(problems), "problems": problems,
            "n_cross_pool_group_overlaps": 0}


def _ci(values):
    vals = [v for v in values if v == v]
    if not vals:
        return {"mean": _NAN, "half_width": _NAN, "lo": _NAN, "hi": _NAN, "n": 0, "n_finite": 0,
                "n_total": len(values)}
    return {**t_ci(vals), "n_finite": len(vals), "n_total": len(values)}


def aggregate_budget(records):
    """Per-condition means with t-intervals over seeds, plus paired differences (descriptive)."""
    by = {c: {r["seed"]: r for r in records if r["condition"] == c} for c in CONDITION_NAMES}
    agg = {"recovery_auc": {}, "stable_reference_effect": {}, "reason_counts": {},
           "n_promotions": {}, "wall_clock_s": {}}
    for c, runs in by.items():
        if not runs:
            continue
        agg["recovery_auc"][c] = _ci([r["summary"]["recovery"]["auc"] for r in runs.values()])
        agg["stable_reference_effect"][c] = {
            "final_stable_macro_f1_drop": _ci(
                [r["summary"]["stable_reference_effect"]["final_stable_macro_f1_drop"]
                 for r in runs.values()]),
            "final_benign_fpr_increase": _ci(
                [r["summary"]["stable_reference_effect"]["final_benign_fpr_increase"]
                 for r in runs.values()])}
        total = Counter()
        for r in runs.values():
            total.update(r["summary"]["reason_counts"])
        agg["reason_counts"][c] = dict(total)
        agg["n_promotions"][c] = _ci([float(r["summary"]["n_promotions"]) for r in runs.values()])
        agg["wall_clock_s"][c] = round(sum(r["timings"]["total_s"] for r in runs.values()), 1)

    def paired(a, b):
        seeds = sorted(set(by[a]) & set(by[b]))
        return {"seeds": seeds,
                "recovery_auc_diff": _ci([by[a][s]["summary"]["recovery"]["auc"]
                                          - by[b][s]["summary"]["recovery"]["auc"]
                                          for s in seeds])}

    agg["paired_descriptive_not_an_h1_test"] = {
        "REAL_ONLY_minus_FROZEN": paired("REAL_ONLY", "FROZEN"),
        "REAL_ONLY_ALL_LABELS_minus_REAL_ONLY": paired("REAL_ONLY_ALL_LABELS", "REAL_ONLY")}
    return agg


def run_p0(data, *, scenario="S1", budgets=None, seeds=None, params=None, scenario_cfg=None,
           out_dir=None, make_conds=make_conditions, cache_provenance=None, progress=None):
    """Run the whole P0 grid in memory; write files if `out_dir` is given. Returns
    {"budget_files": {budget: dict}, "summary": dict}."""
    criteria = P0Criteria()
    budgets = tuple(criteria.budgets if budgets is None else budgets)
    seeds = tuple(criteria.seeds if seeds is None else seeds)
    params = params or InterventionParams()
    base_cfg = scenario_cfg or SCENARIOS[scenario]
    progress = progress or (lambda msg: log.info(msg))
    prereg, problems = check_preregistered(base_cfg, budgets, seeds, params, criteria)
    ambiguous = ambiguous_groups(data.group, data.y)
    conflicts = label_conflict_report(data.group, data.y, np.isin(data.day, base_cfg.pre_days),
                                      np.isin(data.day, base_cfg.drift_days))
    header = {"spec_version": SPEC_VERSION, "params_digest": params.digest(),
              "criteria_digest": criteria.digest(), "spec_rules_sha256": spec_rules_sha256(),
              **git_state(), "started_utc": utc_now_iso(), "versions": library_versions(),
              "scenario": base_cfg.name, "seeds": list(seeds), "budgets": list(budgets),
              "conditions": list(CONDITION_NAMES), "preregistered_configuration": prereg,
              "preregistration_problems": problems, "trigger": "oracle (post-drift windows)",
              "criteria": criteria, "params": params,
              "data": {"n_rows": int(len(data.y)), "n_features": int(data.X.shape[1]),
                       "cache": cache_provenance,
                       "label_conflicts_diagnostic_only": conflicts}}
    t_all = time.perf_counter()
    drift_classes = drift_classes_of(data, base_cfg)
    records_by_budget = {b: [] for b in budgets}
    manifests_by_budget = {b: {} for b in budgets}
    manifest_audits, timings = [], {"per_seed_budget": {}}
    kept_manifests = {}          # (budget, seed) -> manifest, for the budget-nesting audit

    for b in budgets:
        cfg = replace(base_cfg, budget=b)
        for seed in seeds:
            t0 = time.perf_counter()
            manifest = build_partitions(data, cfg, seed)
            kept_manifests[(b, seed)] = manifest
            aud = Auditor(data, manifest, ambiguous)
            audit = {**aud.audit_manifest(), "seed": seed, "budget": b,
                     "manifest_digest": manifest.digest()}
            manifest_audits.append(audit)
            manifests_by_budget[b][seed] = {
                "digest": manifest.digest(), "sizes": manifest.sizes(),
                "data_fingerprint": manifest.data_fingerprint, "audit": audit}

            step0 = next(iter(StreamReplay(manifest)))
            st = TrackedState(data, manifest)
            st.ingest(step0)
            t_base = time.perf_counter()
            base = CandidateBuilder(params, seed).build_base(st.view())
            base_fit_s = time.perf_counter() - t_base
            k = len(data.class_names)
            benign = list(data.class_names).index(params.benign_label)
            stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
            base_stats = s_report_stats(base, data, manifest, stable, benign, k, params.s_min)
            for cond in make_conds():
                rec = run_condition(data, manifest, cond, params, base, base_stats, aud,
                                    drift_classes)
                rec["timings"]["base_fit_s"] = round(base_fit_s, 2)
                records_by_budget[b].append(rec)
                progress(f"[B={b} seed={seed} {cond.name}] {rec['timings']['total_s']:.1f}s")
            timings["per_seed_budget"][f"B{b}_seed{seed}"] = round(time.perf_counter() - t0, 1)
            del base, st

    nesting_audits = [audit_budget_nesting(kept_manifests[(lo, s)], kept_manifests[(hi, s)])
                      for s in seeds for lo, hi in zip(sorted(budgets), sorted(budgets)[1:])]
    evaluation = evaluate_p0(records_by_budget, manifest_audits, criteria, prereg, problems,
                             n_min=params.n_min, eps_def=params.eps_def,
                             nesting_audits=nesting_audits)
    timings["total_s"] = round(time.perf_counter() - t_all, 1)

    # Block order is part of the contract: validity -> diagnostics -> data adequacy -> outcome.
    budget_files = {}
    for b in budgets:
        budget_files[b] = {
            "kind": "p0_budget_result", **header, "budget": b,
            "manifests": manifests_by_budget[b],
            "validity": evaluation["validity"],
            "diagnostics": evaluation["diagnostics"],
            "data_adequacy": {**evaluation["data_adequacy"],
                              "this_budget_status": evaluation["data_adequacy"]["statuses"][b]},
            "h1": evaluation["h1"],
            "nesting_audits": nesting_audits,
            "runs": records_by_budget[b],
            "aggregate": aggregate_budget(records_by_budget[b]),
            "timings": {"total_s": timings["total_s"],
                        "run_totals_s": {f"{r['condition']}_seed{r['seed']}": r["timings"]["total_s"]
                                         for r in records_by_budget[b]}},
        }
    summary = {"kind": "p0_summary", **header, "validity": evaluation["validity"],
               "diagnostics": evaluation["diagnostics"],
               "data_adequacy": evaluation["data_adequacy"], "h1": evaluation["h1"],
               "nesting_audits": nesting_audits,
               "aggregate_by_budget": {b: budget_files[b]["aggregate"] for b in budgets},
               "timings": timings}
    if out_dir is not None:
        out_dir = Path(out_dir)
        for b in budgets:
            write_json(out_dir / f"intervention_p0_{base_cfg.name}_B{b}.json", budget_files[b])
        write_json(out_dir / f"intervention_p0_{base_cfg.name}_summary.json", summary)
    return {"budget_files": budget_files, "summary": summary}


# --------------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Run P0 (FROZEN, REAL_ONLY, REAL_ONLY_ALL_LABELS).")
    ap.add_argument("--scenario", default="S1", choices=sorted(SCENARIOS))
    ap.add_argument("--budgets", type=int, nargs="+", default=list(P0Criteria().budgets))
    ap.add_argument("--seeds", type=int, nargs="+", default=list(P0Criteria().seeds))
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--out-dir", default=str(CACHE_PATH.parent.parent))
    ap.add_argument("--min-available-gib", type=float, default=2.5,
                    help="refuse to load the cache below this much available RAM")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    status = cache_status(args.cache)
    if not (status["cache_exists"] and status["provenance_exists"]):
        print(f"BLOCKED: no cache at {args.cache}. Build it once with:\n"
              f"  python -m proteus.intervention.cache build", file=sys.stderr)
        return 2
    try:
        require_memory(args.min_available_gib, "load the cache for P0")
    except MemoryBlocker as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    data = load_cache(args.cache)
    result = run_p0(data, scenario=args.scenario, budgets=args.budgets, seeds=args.seeds,
                    out_dir=args.out_dir, cache_provenance=load_provenance(args.cache),
                    progress=print)
    s = result["summary"]
    print("validity:", {k: (v["pass"] if isinstance(v, dict) else v)
                        for k, v in s["validity"].items()})
    print("H1:", s["h1"]["status"], s["h1"]["outcome"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
