"""P1 runner (SPEC v1.4): replay every arm on the SAME manifests as P0 (B=100), with canary, shadow
scoring and per-window controller traces.

    python -m proteus.intervention.p1 --seeds 0 1 2 3 4 5 6 7 8 9 --out-dir results/p1

Per window t (prequential, as P0): the deployed model predicts W_t and E_t is scored by the RUNNER
(never fed back); then

  * canary (J.2): if a model was promoted at t-1, it and its predecessor both score the labels that
    arrive now (L_{t-1}, never used to build or promote it) and may be rolled back;
  * the arrived labels enter the fit/sel/gate buffers; the V1 audit checks every array of the view;
  * post-drift windows: `arm.decide(view, incumbent, ctx)`; the chosen model is deployed from t+1.

Shadow scoring (U2): every candidate an arm returns in `ArmOutcome.shadow` (th_R, th*, the oracle
ladder) is scored on E_{t+1} -- the window the deployed model is scored on next -- and on S_report,
AFTER `decide` returned. `decide` has no handle to any of it. This separates candidate quality from
certification: a candidate that is better than the deployed model but was never promoted shows up
here and nowhere else.

Result file per seed: header/provenance -> manifest -> runs. Analysis is a separate step
(`analyze_p1.py`); this file makes no statistical claim.
"""
import proteus.config  # noqa: F401 -- must import before numpy/pandas/sklearn to cap BLAS/OMP threads

import argparse
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from proteus.intervention.arms import ArmOutcome, make_arms
from proteus.intervention.cache import (
    CACHE_PATH, MemoryBlocker, cache_status, load_cache, load_provenance, require_memory)
from proteus.intervention.conditions import LABEL_REGIME_BUDGET, DecisionContext
from proteus.intervention.controller import PURPOSE_CANARY
from proteus.intervention.diagnostics import ambiguous_groups
from proteus.intervention.gate14 import canary
from proteus.intervention.learner import CandidateBuilder, compute_affected_region
from proteus.intervention.metrics import confusion
from proteus.intervention.p0 import (
    Auditor, TrackedState, _cells, drift_classes_of, replay_steps, s_report_stats)
from proteus.intervention.p1_spec import (
    ALL_ARMS, P1_SPEC_VERSION, P1Criteria, rules_sha256)
from proteus.intervention.params import InterventionParams
from proteus.intervention.protocol import SCENARIOS, SPEC_VERSION, StreamReplay, build_partitions
from proteus.intervention.provenance import REPO_ROOT, git_state, library_versions, utc_now_iso
from proteus.intervention.serialize import write_json

log = logging.getLogger("proteus.intervention.p1")
_PURPOSE_FROZEN_DIAGNOSTIC = 20
_NAN = float("nan")
P0_SUMMARY = REPO_ROOT / "results" / "intervention_p0_S1_summary.json"
P0_B100 = REPO_ROOT / "results" / "intervention_p0_S1_B100.json"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_repairable_set(summary_path=P0_SUMMARY):
    """R := the repairable set of the frozen P0 (a drift-class set from the all-labels control).
    Analysis-time construct: no arm ever receives it."""
    doc = json.loads(Path(summary_path).read_text())
    return sorted(int(c) for c in doc["validity"]["v4_repairability"]["repairable_set"])


def _score(model, X, y, amb, k):
    p = model.predict(X)
    return {"cells": _cells(confusion(y, p, k)),
            "cells_clean": _cells(confusion(y[~amb], p[~amb], k)),
            "cells_ambig": _cells(confusion(y[amb], p[amb], k))}


def run_arm(data, manifest, arm, params, base, base_stats, aud, drift_classes, stable, benign):
    seed, cfg = manifest.seed, manifest.config
    k = len(data.class_names)
    state = TrackedState(data, manifest)
    incumbent, incumbent_stats = base, base_stats
    pending_canary, pending_shadow = None, {}
    steps, v1 = [], Counter()
    counts = Counter()
    t_start = time.perf_counter()

    for step in replay_steps(data, manifest, arm.label_regime):
        t0 = time.perf_counter()
        e_idx = step.spec.e_idx                                   # evaluation side only
        X_e, y_e = data.X[e_idx], data.y[e_idx]
        amb = np.isin(data.group[e_idx], aud.ambiguous)
        dep = _score(incumbent, X_e, y_e, amb, k)

        shadow_scores = {}
        for name, model in pending_shadow.items():        # candidates built at t-1, scored on E_t
            sc = _score(model, X_e, y_e, amb, k)
            sc["s_report"] = s_report_stats(model, data, manifest, stable, benign, k, params.s_min)
            shadow_scores[name] = sc
        pending_shadow = {}

        rec = {"t": step.t, "phase": step.phase, "controller_active": step.phase == "post",
               "e_n": int(len(e_idx)), "e_conf_cells": dep["cells"],
               "e_cells_clean": dep["cells_clean"], "e_cells_ambig": dep["cells_ambig"],
               "shadow": shadow_scores, "canary": None, "probe": None, "decision": None,
               "region": [], "measurable": [], "eligible": None, "promoted": None,
               "branch": None, "reason": None, "star_reason": None, "k": None,
               "stop_reason": None, "doses": None, "operator": None, "search": None}

        if arm.canary and pending_canary is not None and len(step.arrived_idx):
            new, prev, region, prev_stats = pending_canary
            cd = canary(new, prev, base, data.X[step.arrived_idx], data.y[step.arrived_idx], region,
                        params, np.random.default_rng([seed, step.t, PURPOSE_CANARY]),
                        benign=benign, n_classes=k)
            rec["canary"] = {"rollback": cd.rollback, "reason": cd.reason, "stats": cd.stats}
            counts["canary_checks"] += 1
            if cd.rollback:
                counts["rollbacks"] += 1
                incumbent = prev
                incumbent_stats = prev_stats
        pending_canary = None

        state.ingest(step)
        view = state.view()
        audit = aud.audit_view(state.provenance(), step.t, arm.label_regime)
        v1.update(audit)
        rec.update({"n_arrived_labels": int(len(step.arrived_idx)),
                    "buffer_sizes": state.buffer_sizes(), "evicted_rows": dict(state.evicted),
                    "real_class_counts": np.bincount(view.real_y, minlength=k).tolist(),
                    "v1_audit": audit})
        ctx = DecisionContext(t=step.t, seed=seed, params=params, anchor=base)
        t_decide = 0.0

        if arm.name == "FROZEN":
            info = compute_affected_region(view, incumbent, params,
                                           ctx.rng(_PURPOSE_FROZEN_DIAGNOSTIC))
            rec.update(region=list(info.region), measurable=list(info.measurable))
        if rec["controller_active"]:
            t1 = time.perf_counter()
            out: ArmOutcome = arm.decide(view, incumbent, ctx)
            t_decide = time.perf_counter() - t1
            tr = out.trace
            rec.update(region=list(out.region) or rec["region"],
                       measurable=tr.get("measurable", rec["measurable"]),
                       eligible=None if out.eligible is None else list(out.eligible),
                       promoted=bool(out.promoted), branch=out.branch, reason=out.reason,
                       star_reason=out.star_reason, k=int(out.k), stop_reason=out.stop_reason,
                       doses=tr.get("doses"), operator=tr.get("operator"), search=tr.get("search"),
                       decision=tr.get("decision"), fixed=tr.get("fixed"))
            counts["windows"] += 1
            counts[f"branch_{out.branch}"] += 1
            counts["candidate_fits"] += int(tr.get("candidate_fits") or 0)
            if out.model is not incumbent and out.promoted:
                prev_model, prev_stats = incumbent, incumbent_stats
                incumbent = out.model
                incumbent_stats = s_report_stats(incumbent, data, manifest, stable, benign, k,
                                                 params.s_min)
                if arm.canary:
                    pending_canary = (incumbent, prev_model, out.region, prev_stats)
                counts["promotions"] += 1
            pending_shadow = out.shadow
        elif arm.probe_pre_drift and step.t >= 1:            # NC5: a no-drift window must be a no-op
            out = arm.decide(view, incumbent, ctx)
            rec["probe"] = {"region": list(out.region), "eligible": out.eligible and list(out.eligible),
                            "promoted": bool(out.promoted), "reason": out.reason, "k": int(out.k),
                            "stop_reason": out.stop_reason}
        rec["deployed_is_base"] = incumbent is base
        rec["s_report"] = incumbent_stats
        rec["timings"] = {"decide_s": round(t_decide, 3),
                          "step_s": round(time.perf_counter() - t0, 3)}
        steps.append(rec)

    return {"kind": "p1_run", "arm": arm.name, "label_regime": arm.label_regime,
            "canary_enabled": bool(arm.canary), "is_reference": bool(arm.is_reference),
            "seed": seed, "budget": cfg.budget, "scenario": cfg.name,
            "n_pre_windows": cfg.n_pre_windows, "n_post_windows": cfg.n_post_windows,
            "drift_classes": drift_classes, "manifest_digest": manifest.digest(),
            "v1": {kk: int(v) for kk, v in v1.items()},
            "buffer": {"ingested_rows": dict(state.ingested), "evicted_rows": dict(state.evicted)},
            "counts": dict(counts), "steps": steps,
            "timings": {"total_s": round(time.perf_counter() - t_start, 2)}}


def code_hashes():
    """SHA-256 of every module of the intervention package: the campaign is run from the working
    tree (the repo owner commits at the end), so the git SHA alone does not identify the code."""
    pkg = Path(__file__).parent
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(pkg.glob("*.py"))}


def seed_header(criteria, params, repairable, base_cfg):
    return {"kind": "p1_seed_result", "p1_spec_version": P1_SPEC_VERSION,
            "code_files_sha256": code_hashes(),
            "partition_spec_version": SPEC_VERSION, "p1_criteria_digest": criteria.digest(),
            "p1_rules_sha256": rules_sha256(), "params_digest": params.digest(),
            **git_state(), "started_utc": utc_now_iso(), "versions": library_versions(),
            "scenario": base_cfg.name, "budget": criteria.budget,
            "repairable_set_R": repairable,
            "p0_summary_sha256": _sha(P0_SUMMARY) if P0_SUMMARY.exists() else None,
            "criteria": criteria, "params": params}


def run_seed(data, seed, arm_names, criteria, params, base_cfg, repairable, out_dir, ambiguous,
             progress=print, tag_preregistered=True):
    cfg = replace(base_cfg, budget=criteria.budget)
    manifest = build_partitions(data, cfg, seed)
    aud = Auditor(data, manifest, ambiguous)
    audit = {**aud.audit_manifest(), "seed": seed, "manifest_digest": manifest.digest()}
    p0_digest = None
    if P0_B100.exists() and seed in criteria.p0_paired_seeds and base_cfg.name == "S1":
        p0_digest = json.loads(P0_B100.read_text())["manifests"][str(seed)]["digest"]
    step0 = next(iter(StreamReplay(manifest)))
    st = TrackedState(data, manifest)
    st.ingest(step0)
    t_b = time.perf_counter()
    base = CandidateBuilder(params, seed).build_base(st.view())
    base_fit_s = time.perf_counter() - t_b
    k = len(data.class_names)
    benign = list(data.class_names).index(params.benign_label)
    stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
    base_stats = s_report_stats(base, data, manifest, stable, benign, k, params.s_min)
    drift_classes = drift_classes_of(data, base_cfg)
    runs = []
    for arm in make_arms(arm_names):
        rec = run_arm(data, manifest, arm, params, base, base_stats, aud, drift_classes, stable,
                      benign)
        rec["timings"]["base_fit_s"] = round(base_fit_s, 2)
        runs.append(rec)
        progress(f"[seed={seed} {arm.name}] {rec['timings']['total_s']:.1f}s "
                 f"promotions={rec['counts'].get('promotions', 0)} "
                 f"rollbacks={rec['counts'].get('rollbacks', 0)}")
    prereg = (tag_preregistered and tuple(arm_names) == tuple(ALL_ARMS)
              and seed in criteria.seeds and params.digest() == InterventionParams().digest()
              and criteria.digest() == P1Criteria().digest()
              and replace(base_cfg, budget=0) == replace(SCENARIOS["S1"], budget=0))
    doc = {**seed_header(criteria, params, repairable, base_cfg), "seed": seed,
           "preregistered_configuration": bool(prereg),
           "manifest": {"digest": manifest.digest(), "sizes": manifest.sizes(), "audit": audit,
                        "p0_manifest_digest": p0_digest,
                        "matches_p0_manifest": (p0_digest == manifest.digest()
                                                if p0_digest else None)},
           "base_stats": base_stats, "runs": runs}
    path = Path(out_dir) / f"intervention_p1_{base_cfg.name}_B{criteria.budget}_seed{seed}.json"
    write_json(path, doc)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the P1 arms (SPEC v1.4).")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(P1Criteria().seeds))
    ap.add_argument("--arms", nargs="+", default=list(ALL_ARMS))
    ap.add_argument("--scenario", default="S1", choices=sorted(SCENARIOS))
    ap.add_argument("--budget", type=int, default=P1Criteria().budget)
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "results" / "p1"))
    ap.add_argument("--p0-summary", default=str(P0_SUMMARY))
    ap.add_argument("--min-available-gib", type=float, default=2.5)
    ap.add_argument("--force", action="store_true", help="overwrite existing seed files")
    ap.add_argument("--smoke", action="store_true",
                    help="mark the run non-preregistered (bug-finding only)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    status = cache_status(args.cache)
    if not (status["cache_exists"] and status["provenance_exists"]):
        print(f"BLOCKED: no cache at {args.cache}", file=sys.stderr)
        return 2
    try:
        require_memory(args.min_available_gib, "load the cache for P1")
    except MemoryBlocker as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    data = load_cache(args.cache)
    criteria = replace(P1Criteria(), scenario=args.scenario, budget=args.budget)
    params = InterventionParams()
    base_cfg = SCENARIOS[args.scenario]
    repairable = load_repairable_set(args.p0_summary)
    ambiguous = ambiguous_groups(data.group, data.y)
    out_dir = Path(args.out_dir)
    for seed in args.seeds:
        path = out_dir / f"intervention_p1_{base_cfg.name}_B{criteria.budget}_seed{seed}.json"
        if path.exists() and not args.force:
            print(f"skip seed {seed}: {path} exists")
            continue
        p = run_seed(data, seed, args.arms, criteria, params, base_cfg, repairable, out_dir,
                     ambiguous, progress=print, tag_preregistered=not args.smoke)
        print("wrote", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
