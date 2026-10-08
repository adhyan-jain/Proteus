"""P1 analysis (SPEC v1.4): turns per-seed result files into the preregistered tests and tables.

    python -m proteus.intervention.analyze_p1 --in-dir results/p1 --out results/intervention_p1_S1_B100_summary.json

Pure function of the result files (plus the frozen P0 files for R, class names and the P0
reconciliation). Nothing is tuned here: every threshold comes from `P1Criteria`, `InterventionParams`
and the preregistration text. The verdict block is mechanical (it applies the fixed-sequence rules);
interpretation belongs in the paper.
"""
import proteus.config  # noqa: F401 -- must import before numpy/scipy

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from proteus.intervention.metrics import f1_from_conf, t_ci
from proteus.intervention.p1_spec import (
    ABLATION_ARMS, CONTROL_ARMS, MAIN_ARMS, REFERENCE_ARMS, P1Criteria, P1_SPEC_VERSION,
    rules_sha256)
from proteus.intervention.params import InterventionParams
from proteus.intervention.provenance import REPO_ROOT, git_state, utc_now_iso
from proteus.intervention.serialize import from_jsonable, loads_strict, write_json

NAN = float("nan")


# ----------------------------------------------------------------------------------- cell maths
def conf(cells, k):
    c = np.zeros((k, k))
    for i, j, n in cells:
        c[i, j] = n
    return c


def window_r_f1(cells, R, s_min, k):
    c = conf(cells, k)
    cls = [x for x in R if c[x].sum() >= s_min]
    return float(f1_from_conf(c)[cls].mean()) if cls else NAN


def recall_of(cells, cls, k):
    c = conf(cells, k)
    n = c[cls].sum()
    return (c[cls, cls] / n) if n else NAN, n


def fin(xs):
    return [x for x in xs if x == x]


def mean(xs):
    xs = fin(xs)
    return float(np.mean(xs)) if xs else NAN


# ----------------------------------------------------------------------------------- loading
def load_seed_files(in_dir, scenario="S1", budget=100):
    docs = {}
    for p in sorted(Path(in_dir).glob(f"intervention_p1_{scenario}_B{budget}_seed*.json")):
        d = from_jsonable(loads_strict(p.read_text()))
        docs[int(d["seed"])] = d
    return docs


def p0_reference(p0_dir):
    summ = loads_strict((p0_dir / "intervention_p0_S1_summary.json").read_text())
    b100 = from_jsonable(loads_strict((p0_dir / "intervention_p0_S1_B100.json").read_text()))
    return summ, b100


# ----------------------------------------------------------------------------------- per-run metrics
def run_metrics(run, R, s_min, k, base_stats, params):
    n_pre = run["n_pre_windows"]
    steps = run["steps"]
    post = [s for s in steps if s["t"] > n_pre]
    dep = [window_r_f1(s["e_conf_cells"], R, s_min, k) for s in post]
    matched = [s for s in post if s["t"] >= n_pre + 2]
    dep_m = [window_r_f1(s["e_conf_cells"], R, s_min, k) for s in matched]

    def best_shadow(s, keys):
        cands = [s["shadow"][x] for x in keys if x in s["shadow"]]
        if not cands:
            return window_r_f1(s["e_conf_cells"], R, s_min, k)
        return window_r_f1(cands[0]["cells"], R, s_min, k)

    sh_star = [best_shadow(s, ["theta_star", "theta_R"]) for s in matched]
    sh_real = [window_r_f1(s["shadow"]["theta_R"]["cells"], R, s_min, k)
               if "theta_R" in s["shadow"] else window_r_f1(s["e_conf_cells"], R, s_min, k)
               for s in matched]
    oracle = []
    for s in matched:
        vals = [window_r_f1(v["cells"], R, s_min, k) for key, v in s["shadow"].items()
                if key == "theta_R" or key.startswith("rho")]
        oracle.append(max(fin(vals)) if fin(vals) else window_r_f1(s["e_conf_cells"], R, s_min, k))

    # v1.3 secondary endpoint (region fixed after the fact: drift classes with pooled E support)
    drift = run["drift_classes"]
    pooled = sum(conf(s["e_conf_cells"], k) for s in post)
    region = [c for c in drift if pooled[c].sum() >= s_min]
    auc_w = []
    for s in post:
        c = conf(s["e_conf_cells"], k)
        cls = [x for x in region if c[x].sum() > 0]
        auc_w.append(float(f1_from_conf(c)[cls].mean()) if cls else NAN)

    # safety on S_report for deployed models
    breaches, worst_drop, worst_fpr, safe_windows = 0, 0.0, 0.0, 0
    for s in post:
        sr = s["s_report"]
        if s["deployed_is_base"] or sr is None:
            continue
        safe_windows += 1
        drop = base_stats["stable_macro_f1"] - sr["stable_macro_f1"]
        inc = sr["benign_fpr"] - base_stats["benign_fpr"]
        worst_drop, worst_fpr = max(worst_drop, drop), max(worst_fpr, inc)
        breaches += int(drop > params.eps_s or inc > params.eps_fpr)

    # per-class recall pooled over post windows (deployed and shadow th_R), clean vs ambiguous rows
    def pooled_cells(key, sub):
        tot = np.zeros((k, k))
        for s in matched:
            if key == "deployed":
                tot += conf(s[{"all": "e_conf_cells", "clean": "e_cells_clean",
                               "ambig": "e_cells_ambig"}[sub]], k)
            elif key in s["shadow"]:
                tot += conf(s["shadow"][key][{"all": "cells", "clean": "cells_clean",
                                              "ambig": "cells_ambig"}[sub]], k)
            else:
                tot += conf(s[{"all": "e_conf_cells", "clean": "e_cells_clean",
                               "ambig": "e_cells_ambig"}[sub]], k)
        return tot

    recall = {}
    for key in ("deployed", "theta_R", "theta_star"):
        recall[key] = {}
        for sub in ("all", "clean", "ambig"):
            tot = pooled_cells(key, sub)
            recall[key][sub] = {str(c): {"recall": (tot[c, c] / tot[c].sum()) if tot[c].sum() else NAN,
                                         "n": float(tot[c].sum())} for c in R}

    counts = run["counts"]
    active = [s for s in post]
    reasons = Counter(s["reason"] for s in active if s["reason"])
    star_reasons = Counter(s["star_reason"] for s in active if s["star_reason"])
    stops = Counter(s["stop_reason"] for s in active if s["stop_reason"])
    ks = [s["k"] for s in active if s["k"] is not None]
    n_eligible = [s for s in active if s["eligible"]]
    alloc = Counter()
    for s in active:
        for c, r in (s["doses"] or {}).items():
            alloc[str(c)] += int(r > 0)
    return {
        "r_recovery": mean(dep), "r_recovery_windows": dep,
        "r_recovery_matched": mean(dep_m), "shadow_candidate": mean(sh_star),
        "shadow_real_only_candidate": mean(sh_real), "shadow_oracle_best": mean(oracle),
        "v13_auc": mean(auc_w), "v13_auc_region": region,
        "safety": {"breaches": breaches, "deployed_nonbase_windows": safe_windows,
                   "worst_stable_f1_drop": worst_drop, "worst_benign_fpr_increase": worst_fpr},
        "recall": recall,
        "counts": {kk: int(v) for kk, v in counts.items()},
        "reasons": dict(reasons), "star_reasons": dict(star_reasons), "stop_reasons": dict(stops),
        "mean_k": mean([float(x) for x in ks]),
        "controller_runs_with_eligible": len(n_eligible),
        "controller_runs_with_eligible_k0": sum(1 for s in n_eligible if s["k"] == 0),
        "class_allocation": dict(alloc),
        "star_promotions": int(sum(1 for s in active if s["branch"] == "star")),
        "real_promotions": int(sum(1 for s in active if s["branch"] == "real_only")),
        "rollbacks": int(counts.get("rollbacks", 0)), "canary_checks": int(counts.get("canary_checks", 0)),
        "wall_clock_s": run["timings"]["total_s"],
    }


# ----------------------------------------------------------------------------------- statistics
def paired(per_seed, a, b, key, seeds):
    xs = [per_seed[a][s][key] - per_seed[b][s][key] for s in seeds]
    ci = t_ci(fin(xs)) if len(fin(xs)) == len(xs) else {"mean": NAN, "lo": NAN, "hi": NAN,
                                                        "half_width": NAN, "n": len(fin(xs))}
    return {"diff": ci, "per_seed": dict(zip(map(str, seeds), xs)),
            "a_mean": mean([per_seed[a][s][key] for s in seeds]),
            "b_mean": mean([per_seed[b][s][key] for s in seeds])}


def arm_ci(per_seed, a, key, seeds):
    return t_ci(fin([per_seed[a][s][key] for s in seeds]))


def reject(p):
    return bool(p["diff"]["lo"] == p["diff"]["lo"] and p["diff"]["lo"] > 0)


# ----------------------------------------------------------------------------------- main analysis
def analyze(docs, p0_dir, criteria=None, params=None):
    criteria = criteria or P1Criteria()
    params = params or InterventionParams()
    p0_summary, p0_b100 = p0_reference(p0_dir)
    class_names = p0_summary["data"]["cache"]["class_names"]
    k = len(class_names)
    seeds = sorted(docs)
    R = sorted(docs[seeds[0]]["repairable_set_R"])
    assert all(sorted(d["repairable_set_R"]) == R for d in docs.values())
    s_min = params.s_min
    arms = [r["arm"] for r in docs[seeds[0]]["runs"]]

    per_seed = {a: {} for a in arms}
    base_stats = {s: docs[s]["base_stats"] for s in seeds}
    for s in seeds:
        for run in docs[s]["runs"]:
            per_seed[run["arm"]][s] = run_metrics(run, R, s_min, k, base_stats[s], params)

    prov = {
        "seeds_present": seeds, "complete": seeds == list(criteria.seeds),
        "all_preregistered": all(d["preregistered_configuration"] for d in docs.values()),
        "git_shas": sorted({d["git_sha"] for d in docs.values()}),
        "git_dirty_any": any(d["git_dirty"] for d in docs.values()),
        "p1_spec_version": sorted({d["p1_spec_version"] for d in docs.values()}),
        "p1_rules_sha256": sorted({d["p1_rules_sha256"] for d in docs.values()}),
        "p1_rules_sha256_now": rules_sha256(),
        "p1_criteria_digest": sorted({d["p1_criteria_digest"] for d in docs.values()}),
        "params_digest": sorted({d["params_digest"] for d in docs.values()}),
        "repairable_set_R": R, "repairable_set_names": [class_names[c] for c in R],
        "manifest_matches_p0": {str(s): docs[s]["manifest"]["matches_p0_manifest"] for s in seeds},
        "v1_violations": {a: int(sum(sum(d_run["v1"].get("n_violations", 0) for d_run in [r])
                                     for s in seeds for r in docs[s]["runs"] if r["arm"] == a))
                          for a in arms},
        "versions": docs[seeds[0]]["versions"],
    }

    # --- reconciliation with the frozen P0 REAL_ONLY (seeds 0-4) ---------------------------
    recon = {"seeds": [], "identical": True, "problems": []}
    p0_runs = {r["seed"]: r for r in p0_b100["runs"] if r["condition"] == "REAL_ONLY"}
    for s in seeds:
        if s not in p0_runs:
            continue
        mine = next(r for r in docs[s]["runs"] if r["arm"] == "ABL-NO-CANARY-REAL")
        ref = p0_runs[s]
        recon["seeds"].append(s)
        for a, b in zip(ref["steps"], mine["steps"]):
            if (a["t"], a["reason"], a["promoted"], a["region"], a["e_conf_cells"]) != (
                    b["t"], b["reason"], b["promoted"], b["region"], b["e_conf_cells"]):
                recon["identical"] = False
                recon["problems"].append({"seed": s, "t": a["t"]})
    recon["note"] = ("P1's ABL-NO-CANARY-REAL replays the frozen P0 REAL_ONLY decision on the same "
                     "manifest; identical = same reason, promotion, region and E confusion cells at "
                     "every window")

    # --- per-arm table ------------------------------------------------------------------------
    table = {}
    for a in arms:
        row = {"r_recovery": arm_ci(per_seed, a, "r_recovery", seeds),
               "r_recovery_matched": arm_ci(per_seed, a, "r_recovery_matched", seeds),
               "shadow_candidate": arm_ci(per_seed, a, "shadow_candidate", seeds),
               "shadow_real_only_candidate": arm_ci(per_seed, a, "shadow_real_only_candidate", seeds),
               "v13_auc": arm_ci(per_seed, a, "v13_auc", seeds)}
        agg = Counter()
        for s in seeds:
            m = per_seed[a][s]
            for kk in ("reasons", "star_reasons", "stop_reasons", "class_allocation"):
                agg.update({f"{kk}:{x}": v for x, v in m[kk].items()})
        row["promotions"] = {"star": sum(per_seed[a][s]["star_promotions"] for s in seeds),
                             "real_only": sum(per_seed[a][s]["real_promotions"] for s in seeds),
                             "rollbacks": sum(per_seed[a][s]["rollbacks"] for s in seeds),
                             "canary_checks": sum(per_seed[a][s]["canary_checks"] for s in seeds),
                             "seeds_with_star": sum(per_seed[a][s]["star_promotions"] > 0 for s in seeds)}
        row["safety"] = {"breaches": sum(per_seed[a][s]["safety"]["breaches"] for s in seeds),
                         "worst_stable_f1_drop": max(per_seed[a][s]["safety"]["worst_stable_f1_drop"] for s in seeds),
                         "worst_benign_fpr_increase": max(per_seed[a][s]["safety"]["worst_benign_fpr_increase"] for s in seeds),
                         "nonbase_windows": sum(per_seed[a][s]["safety"]["deployed_nonbase_windows"] for s in seeds)}
        row["tallies"] = dict(agg)
        row["wall_clock_s"] = round(sum(per_seed[a][s]["wall_clock_s"] for s in seeds), 1)
        row["candidate_fits"] = sum(per_seed[a][s]["counts"].get("candidate_fits", 0) for s in seeds)
        table[a] = row

    # --- preregistered hypotheses -----------------------------------------------------------
    h = {}
    h2 = paired(per_seed, "CTRL-SMOTE", "REAL_ONLY", "r_recovery", seeds)
    h["H2"] = {**h2, "rejected": reject(h2), "contrast": "CTRL-SMOTE - REAL_ONLY (R-recovery)"}
    chain_ok = h["H2"]["rejected"]
    for name, other in (("H3a", "CTRL-ROS"), ("H3b", "CTRL-THRESH")):
        p = paired(per_seed, "CTRL-SMOTE", other, "r_recovery", seeds)
        h[name] = {**p, "rejected": reject(p), "tested_under_sequence": chain_ok,
                   "contrast": f"CTRL-SMOTE - {other}"}
        chain_ok = chain_ok and h[name]["rejected"]
    fixed = {}
    for rho, an in ((1.0, "FIXED-SMOTE-1"), (4.0, "FIXED-SMOTE-4")):
        p = paired(per_seed, "CTRL-SMOTE", an, "r_recovery", seeds)
        fixed[an] = {**p, "noninferior": bool(p["diff"]["lo"] >= -params.eps_ni),
                     "established_inferior": bool(p["diff"]["hi"] < -params.eps_ni)}
    h["H5"] = {"per_fixed": fixed, "tested_under_sequence": chain_ok,
               "noninferior_to_all": all(v["noninferior"] for v in fixed.values())}
    star_seeds = [s for s in seeds if per_seed["CTRL-SMOTE"][s]["star_promotions"] > 0]
    breaches = sum(per_seed["CTRL-SMOTE"][s]["safety"]["breaches"] for s in seeds)
    h["H4"] = {"s_report_breaches": breaches, "seeds_with_star_promotion": len(star_seeds),
               "activity_required": criteria.activity_min_seeds,
               "passed": bool(breaches == 0 and len(star_seeds) >= criteria.activity_min_seeds),
               "safe_by_inaction": bool(breaches == 0 and len(star_seeds) < criteria.activity_min_seeds)}

    # --- failure / reporting conditions ------------------------------------------------------
    sh = paired(per_seed, "CTRL-SMOTE", "REAL_ONLY", "shadow_candidate", seeds)
    ctrl_runs = sum(per_seed["CTRL-SMOTE"][s]["controller_runs_with_eligible"] for s in seeds)
    ctrl_k0 = sum(per_seed["CTRL-SMOTE"][s]["controller_runs_with_eligible_k0"] for s in seeds)
    tot_prom = (table["CTRL-SMOTE"]["promotions"]["star"] + table["CTRL-SMOTE"]["promotions"]["real_only"])
    go_classes = [int(c) for c in (p0_summary.get("diagnostics", {}).get("label_ambiguity", {})
                                   .get("go_classes", {}))] or list(R)     # the P0 GO class(es)
    ro_clean = []
    for s in seeds:
        for c in go_classes:
            r_ = per_seed["REAL_ONLY"][s]["recall"]["theta_R"]["clean"][str(c)]
            if r_["n"]:
                ro_clean.append((r_["recall"] * r_["n"], r_["n"]))
    ps_clean_recall = (sum(a for a, _ in ro_clean) / sum(n for _, n in ro_clean)) if ro_clean else NAN
    nc = {}
    for a in [x for x in CONTROL_ARMS if x in per_seed]:
        p = paired(per_seed, a, "REAL_ONLY", "r_recovery", seeds)
        nc[a] = {**p, "beats_real_only": reject(p)}
    flags = {
        "F2_H2_not_rejected": not h["H2"]["rejected"],
        "F3a_H3a_not_rejected": not h["H3a"]["rejected"], "F3b_H3b_not_rejected": not h["H3b"]["rejected"],
        "F4_unsafe_or_rollbacks": bool(breaches > 0 or (tot_prom and
                                       table["CTRL-SMOTE"]["promotions"]["rollbacks"] > criteria.rollback_share_max * tot_prom)),
        "F5_established_inferior_to_fixed": any(v["established_inferior"] for v in fixed.values()),
        "F8_degenerate_controller": bool(ctrl_runs and ctrl_k0 / ctrl_runs > criteria.degenerate_k0_share),
        "F9_ambiguity_bound": bool(ps_clean_recall == ps_clean_recall and (1 - ps_clean_recall) <= params.eps_def),
        "F10_certification_bottleneck": bool(reject(sh) and not h["H2"]["rejected"]),
        "F11_negative_control_beats_real_only": any(v["beats_real_only"] for v in nc.values()),
    }
    details = {"controller_runs_with_eligible": ctrl_runs, "controller_runs_k0": ctrl_k0,
               "ctrl_smote_promotions": tot_prom, "shadow_vs_real_only": sh,
               "go_classes": go_classes,
               "go_class_clean_row_recall_of_real_only_theta_R": ps_clean_recall}

    # --- descriptive contrasts ---------------------------------------------------------------
    vs_real = {a: paired(per_seed, a, "REAL_ONLY", "r_recovery", seeds) for a in arms if a != "REAL_ONLY"}
    vs_ctrl = {a: paired(per_seed, a, "CTRL-SMOTE", "r_recovery", seeds) for a in arms if a != "CTRL-SMOTE"}
    shadow_vs_real = {a: paired(per_seed, a, "REAL_ONLY", "shadow_candidate", seeds)
                      for a in arms if a not in ("REAL_ONLY",)}

    # --- curves for the presentation layer ---------------------------------------------------
    curves = {}
    n_post = len(per_seed[arms[0]][seeds[0]]["r_recovery_windows"])
    for a in arms:
        w = np.array([per_seed[a][s]["r_recovery_windows"] for s in seeds], dtype=float)
        curves[a] = {"mean": [float(np.nanmean(w[:, i])) for i in range(n_post)],
                     "sd": [float(np.nanstd(w[:, i], ddof=1)) for i in range(n_post)]}

    # --- allocation / stopping / step-safety diagnostics ------------------------------------
    steps_diag = {"candidates": 0, "safe": 0, "anchor_would_block_stable": 0,
                  "anchor_would_block_fpr": 0, "gain_lcb_positive": 0}
    for s in seeds:
        for run in docs[s]["runs"]:
            if run["arm"] != "CTRL-SMOTE":
                continue
            for st in run["steps"]:
                for it in (st["search"] or []):
                    for c in it["candidates"]:
                        steps_diag["candidates"] += 1
                        steps_diag["safe"] += int(c["safe"])
                        steps_diag["gain_lcb_positive"] += int(c["gain_lcb"] == c["gain_lcb"] and c["gain_lcb"] > 0)
                        a_s, a_f = c["anchor_d_stable_s_ucb"], c["anchor_d_fpr_s_ucb"]
                        steps_diag["anchor_would_block_stable"] += int(a_s == a_s and a_s > params.eps_s)
                        steps_diag["anchor_would_block_fpr"] += int(a_f == a_f and a_f > params.eps_fpr)
    probe = {"windows": 0, "nonempty_region": 0, "promoted": 0}
    for s in seeds:
        run = next(r for r in docs[s]["runs"] if r["arm"] == "CTRL-SMOTE")
        for st in run["steps"]:
            if st["probe"]:
                probe["windows"] += 1
                probe["nonempty_region"] += int(bool(st["probe"]["region"]))
                probe["promoted"] += int(st["probe"]["promoted"])

    ablations = {a: {"vs_ctrl_smote": vs_ctrl[a], "vs_real_only": vs_real[a]} for a in ABLATION_ARMS if a in arms}
    verdict = mechanical_verdict(h, flags, prov)

    return {
        "kind": "p1_summary", "p1_spec_version": P1_SPEC_VERSION, **git_state(),
        "analysed_utc": utc_now_iso(), "scenario": "S1", "budget": criteria.budget,
        "criteria_digest": criteria.digest(), "provenance": prov, "p0_reconciliation": recon,
        "class_names": class_names,
        "primary_endpoint": "R-recovery: mean over post-drift windows of mean E-F1 over repairable classes",
        "arm_table": table, "hypotheses": h, "flags": flags, "flag_details": details,
        "negative_controls": nc, "ablations": ablations,
        "references": {a: {"vs_real_only": vs_real[a]} for a in REFERENCE_ARMS if a in arms},
        "main_arms_vs_real_only": {a: vs_real[a] for a in MAIN_ARMS if a in vs_real},
        "shadow_vs_real_only": shadow_vs_real, "step_filter_diagnostics": steps_diag,
        "pre_drift_probe": probe, "gate_blocking_exploratory": gate_blocking(docs),
        "curves_r_f1_by_post_window": curves,
        "per_seed": {a: {str(s): {kk: v for kk, v in per_seed[a][s].items()
                                  if kk not in ("r_recovery_windows",)} for s in seeds} for a in arms},
        "verdict": verdict,
    }


DECISION_ARMS = ("REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "CTRL-ROS", "FIXED-SMOTE-4")


def decision_traces(docs, arms=DECISION_ARMS):
    """Compact per-window controller decisions for the presentation layer (artifact-backed)."""
    out = {}
    for a in arms:
        out[a] = {}
        for s in sorted(docs):
            run = next((r for r in docs[s]["runs"] if r["arm"] == a), None)
            if run is None:
                continue
            rows = []
            for st in run["steps"]:
                if st["phase"] != "post":
                    continue
                rows.append({
                    "t": st["t"], "region": st["region"], "eligible": st["eligible"], "k": st["k"],
                    "stop_reason": st["stop_reason"], "branch": st["branch"], "reason": st["reason"],
                    "star_reason": st["star_reason"], "promoted": st["promoted"],
                    "doses": st["doses"], "n_syn": (st["operator"] or {}).get("n_syn"),
                    "canary": (st["canary"] or {}).get("reason"),
                    "rollback": bool((st["canary"] or {}).get("rollback")),
                    "deployed_is_base": st["deployed_is_base"],
                    "search": [{"k": it["k"], "accepted": it["accepted"],
                                "candidates": [{kk: c[kk] for kk in (
                                    "c", "rung", "n_syn_after", "gain_lcb", "gain_point", "safe",
                                    "d_fpr_sel_ucb", "d_stable_s_ucb", "d_fpr_s_ucb")}
                                    for c in it["candidates"]]} for it in (st["search"] or [])]})
            out[a][str(s)] = rows
    return out


def gate_blocking(docs, arms=("REAL_ONLY", "CTRL-SMOTE", "FIXED-SMOTE-4", "REAL_ONLY_ALL_LABELS")):
    """Exploratory (not preregistered): which gate criterion blocks the candidates that were rejected,
    and how much benign evidence the gate had when it did. Read from the per-window reports."""
    out = {}
    for a in arms:
        crit, n_ben, n_gate, rejected, util_ok_env_fail = Counter(), [], [], 0, 0
        for s in sorted(docs):
            run = next((r for r in docs[s]["runs"] if r["arm"] == a), None)
            if run is None:
                continue
            for st in run["steps"]:
                dec = st.get("decision") or {}
                rep = dec.get("report") or dec.get("real_decision", {}) and (dec["real_decision"].get("report"))
                if st["phase"] != "post" or not rep or st.get("promoted"):
                    continue
                failed = rep.get("failed") or []
                rejected += 1
                crit.update(failed)
                n_ben.append(rep["n_gate_benign"])
                n_gate.append(rep["n_gate_rows"])
                util_ok_env_fail += int(rep["utility_status"] == "ok" and any(
                    c in failed for c in ("stable_f1", "fpr_stable", "fpr_current")))
        out[a] = {"rejected_with_report": rejected, "failed_criteria": dict(crit),
                  "utility_ok_but_envelope_failed": util_ok_env_fail,
                  "median_gate_benign_rows": float(np.median(n_ben)) if n_ben else NAN,
                  "median_gate_rows": float(np.median(n_gate)) if n_gate else NAN,
                  "one_extra_benign_fp_moves_fpr_by": (1.0 / float(np.median(n_ben))) if n_ben else NAN}
    return out


def mechanical_verdict(h, flags, prov):
    if not h["H2"]["rejected"]:
        branch = "NEGATIVE: H2 not rejected; fixed sequence stops; P2 (WGAN) cancelled"
    elif not (h["H3a"]["rejected"] and h["H3b"]["rejected"]):
        branch = ("PARTIAL: H2 rejected but the gain is not attributable to synthetic content "
                  "(H3a/H3b not both rejected); P2 cancelled")
    else:
        branch = "POSITIVE: H2, H3a and H3b rejected; P2 (WGAN) is unlocked"
    return {"branch": branch, "p2_unlocked": bool(h["H2"]["rejected"] and h["H3a"]["rejected"]
                                                  and h["H3b"]["rejected"]),
            "fired_flags": sorted(k for k, v in flags.items() if v),
            "complete_and_preregistered": bool(prov["complete"] and prov["all_preregistered"])}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default=str(REPO_ROOT / "results" / "p1"))
    ap.add_argument("--p0-dir", default=str(REPO_ROOT / "results"))
    ap.add_argument("--out", default=str(REPO_ROOT / "results" / "intervention_p1_S1_B100_summary.json"))
    ap.add_argument("--scenario", default="S1")
    ap.add_argument("--decisions-out", default=None)
    args = ap.parse_args(argv)
    docs = load_seed_files(args.in_dir, args.scenario)
    if not docs:
        print("no seed files", file=sys.stderr)
        return 2
    out = analyze(docs, Path(args.p0_dir))
    write_json(args.out, out)
    dec_path = args.decisions_out or str(Path(args.out).with_name(
        Path(args.out).name.replace("_summary", "_decisions")))
    write_json(dec_path, {"kind": "p1_decisions", "p1_spec_version": P1_SPEC_VERSION,
                          "class_names": out["class_names"], "traces": decision_traces(docs)})
    v = out["verdict"]
    print(v["branch"], "| flags:", v["fired_flags"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
