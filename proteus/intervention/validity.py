"""P0 validity, data adequacy and the outcome state machine (SPEC v1.2, section L.1).

The normative text is `docs/INTERVENTION_SPEC.md` section L.1 (between the P0-DECISION-RULES
markers); this module only implements it, and `spec_rules_sha256()` hashes that text into every
result so the rules a result was produced under are identifiable. Everything here is a pure
function of result records produced by `p0.py`: nothing reads data and nothing is tuned.

Four blocks, kept separate and emitted in this order (validity -> diagnostics -> data adequacy ->
outcome):

  validity      V1 leakage/partition integrity, V3 integrity (FROZEN sees every measurable drift
                class), V4 repairability (non-empty repairable set R). Any failure => INVALID.
  diagnostics   V2 null region, cross-pool duplicates, conflicting labels. Mandatory, reported
                before the outcome, never gate it. V2 blocks P1, not P0.
  data adequacy per-budget status GO / NO_ROOM / UNMEASURABLE from one criterion: could the
                preregistered GO criterion have been met at that budget? Insufficient support
                means UNMEASURABLE, never INVALID.
  outcome       INVALID > GO > NO_GO_NO_ROOM > INCONCLUSIVE_UNMEASURABLE, only for the
                preregistered configuration.

Definitions: t_d = n_pre_windows; post-drift windows are t > t_d (t_d sees only pre-drift labels);
drift classes D = classes absent from the pre-drift pool; "final window" = the last step.
"""
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from proteus.intervention.protocol import SPEC_VERSION
from proteus.intervention.provenance import REPO_ROOT

OUTCOMES = ("INVALID", "GO", "NO_GO_NO_ROOM", "INCONCLUSIVE_UNMEASURABLE")
STATUSES = ("GO", "NO_ROOM", "UNMEASURABLE")

SPEC_PATH = REPO_ROOT / "docs" / "INTERVENTION_SPEC.md"
_BEGIN, _END = "<!-- P0-DECISION-RULES:BEGIN -->", "<!-- P0-DECISION-RULES:END -->"
_NAN = float("nan")


def spec_rules_text(path=SPEC_PATH):
    text = Path(path).read_text()
    if _BEGIN not in text or _END not in text:
        raise RuntimeError(f"{path} has no P0-DECISION-RULES section")
    return text.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()


def spec_rules_sha256(path=SPEC_PATH):
    return hashlib.sha256(spec_rules_text(path).encode()).hexdigest()


@dataclass(frozen=True)
class P0Criteria:
    """The constants of spec L.1 (pinned by a test). Do not tune."""
    scenario: str = "S1"
    budgets: tuple = (25, 100)
    seeds: tuple = (0, 1, 2, 3, 4)
    v2_min_seeds_empty: int = 4        # V2 diagnostic: A_FROZEN empty at last pre-drift window
    repairable_min_seeds: int = 3      # R: a drift class repaired in >= 3 of 5 seeds
    adequate_min_windows: int = 2      # assessable cells per seed ...
    adequate_min_seeds: int = 3        # ... in >= 3 seeds => NO_ROOM-or-better
    go_min_windows: int = 2            # GO cells per seed ...
    go_min_seeds: int = 3              # ... in >= 3 seeds => GO

    def digest(self):
        payload = json.dumps({"spec_version": SPEC_VERSION, "criteria": asdict(self),
                              "outcomes": OUTCOMES, "statuses": STATUSES},
                             sort_keys=True, default=list)
        return hashlib.sha256(payload.encode()).hexdigest()


def _by_seed(records, condition):
    return {r["seed"]: r for r in records if r["condition"] == condition}


def _post_steps(rec):
    """Post-drift windows after t_d."""
    return [s for s in rec["steps"] if s["t"] > rec["n_pre_windows"]]


def _drift_union(records):
    return sorted({c for r in records for c in r["drift_classes"]})


# ------------------------------------------------------------------------------------------ V1
def check_v1(records, manifest_audits, nesting_audits=()):
    """Leakage and partition integrity. Cross-pool duplicates are counted, never failed."""
    run_violations = sum(r["v1"]["n_violations"] for r in records)
    manifest_violations = sum(a["n_same_pool_group_overlaps"] for a in manifest_audits)
    nesting_violations = sum(a["n_violations"] for a in nesting_audits)
    cross = sum(r["v1"]["n_cross_pool_group_overlaps"] for r in records)
    cross += sum(a["n_cross_pool_group_overlaps"] for a in manifest_audits)
    return {"pass": (run_violations == 0 and manifest_violations == 0 and nesting_violations == 0
                     and bool(records)),
            "n_runs_audited": len(records), "n_run_violations": run_violations,
            "n_manifest_violations": manifest_violations,
            "n_budget_nesting_violations": nesting_violations,
            "n_cross_pool_group_overlaps_informational": cross}


# ----------------------------------------------------------------------- repairable set (V4)
def _seed_outcome_for_class(final, c, n_min):
    counts = final["real_class_counts"]
    if c not in final["measurable"]:
        return "unmeasurable"
    if counts[c] < n_min:
        return "thin_real_support"
    return "residual_deficiency" if c in (final.get("eligible") or ()) else "repaired"


def check_v4(records_by_budget, criteria, n_min):
    """Class-wise repairability from REAL_ONLY_ALL_LABELS. Seed s repairs drift class c iff, at the
    final window, c is measurable, has >= n_min real rows and is not in I. R = classes repaired in
    >= `repairable_min_seeds` seeds. V4 passes iff R is non-empty and identical at every budget."""
    per_budget, sets = {}, {}
    for b, recs in records_by_budget.items():
        drift = _drift_union(recs)
        per_class = {c: {"repaired": 0, "residual_deficiency": 0, "thin_real_support": 0,
                         "unmeasurable": 0} for c in drift}
        n_eval = 0
        for seed, rec in sorted(_by_seed(recs, "REAL_ONLY_ALL_LABELS").items()):
            final = rec["steps"][-1] if rec["steps"] else None
            if final is None or not final.get("controller_active"):
                continue
            n_eval += 1
            for c in rec["drift_classes"]:
                per_class[c][_seed_outcome_for_class(final, c, n_min)] += 1
        r_b = sorted(c for c, v in per_class.items()
                     if v["repaired"] >= criteria.repairable_min_seeds)
        sets[b] = r_b
        per_budget[b] = {"n_seeds_evaluated": n_eval, "repairable_set": r_b,
                         "per_class_seed_counts": per_class,
                         "unrepaired_classes": {c: v for c, v in per_class.items()
                                                if c not in r_b}}
    consistent = len({tuple(v) for v in sets.values()}) <= 1
    r = next(iter(sets.values()), []) if consistent else []
    return {"pass": bool(r) and consistent, "repairable_set": r, "budget_independent": consistent,
            "required_seeds": criteria.repairable_min_seeds, "per_budget": per_budget}


# ----------------------------------------------------------------------- cells / budget status
def reo_cells(rec, repairable, n_min):
    """REAL_ONLY post-drift cells: assessable iff some c in R ∩ M_t has n_c >= n_min; GO cell iff
    I_t ∩ R != {}."""
    out = []
    for s in _post_steps(rec):
        counts = s["real_class_counts"]
        measurable = set(s["measurable"])
        assessable = any(c in measurable and counts[c] >= n_min for c in repairable)
        go_classes = sorted(set(s.get("eligible") or ()) & set(repairable))
        out.append({"t": s["t"], "assessable": assessable, "go": bool(go_classes),
                    "go_classes": go_classes})
    return out


def budget_status(recs, repairable, criteria, n_min):
    """Exactly one of GO / NO_ROOM / UNMEASURABLE, from the one criterion 'could GO be reached'."""
    per_seed, inconsistent, n_cells, n_unassessable = {}, [], 0, 0
    for seed, rec in sorted(_by_seed(recs, "REAL_ONLY").items()):
        cells = reo_cells(rec, repairable, n_min)
        bad = [c["t"] for c in cells if c["go"] and not c["assessable"]]
        inconsistent += [{"seed": seed, "t": t} for t in bad]
        n_cells += len(cells)
        n_unassessable += sum(not c["assessable"] for c in cells)
        per_seed[seed] = {"n_cells": len(cells),
                          "n_assessable": sum(c["assessable"] for c in cells),
                          "n_go": sum(c["go"] for c in cells),
                          "go_classes": sorted({k for c in cells for k in c["go_classes"]})}
    n_go = sum(v["n_go"] >= criteria.go_min_windows for v in per_seed.values())
    n_ad = sum(v["n_assessable"] >= criteria.adequate_min_windows for v in per_seed.values())
    status = ("GO" if n_go >= criteria.go_min_seeds
              else "NO_ROOM" if n_ad >= criteria.adequate_min_seeds else "UNMEASURABLE")
    return {"status": status, "n_seeds_with_go": n_go, "n_seeds_assessable": n_ad,
            "go_required": [criteria.go_min_windows, criteria.go_min_seeds],
            "assessable_required": [criteria.adequate_min_windows, criteria.adequate_min_seeds],
            "per_seed": per_seed,
            "unmeasurable_cell_fraction_descriptive": (n_unassessable / n_cells) if n_cells else _NAN,
            "inconsistent_go_cells": inconsistent}


# ------------------------------------------------------------------------------ V3 integrity
def check_v3_integrity(records_by_budget, inconsistent_go_cells):
    """FROZEN cannot predict a class absent from D_ref, so every measurable drift class must be in
    its affected region at every post-drift window. Any exception is a pipeline defect."""
    violations, checked = [], 0
    for b, recs in records_by_budget.items():
        for seed, rec in sorted(_by_seed(recs, "FROZEN").items()):
            drift = set(rec["drift_classes"])
            for s in _post_steps(rec):
                for c in sorted(drift & set(s["measurable"])):
                    checked += 1
                    if c not in s["region"]:
                        violations.append({"budget": b, "seed": seed, "t": s["t"], "class": c})
    return {"pass": not violations and not inconsistent_go_cells,
            "n_cells_checked": checked, "violations": violations,
            "go_cells_not_assessable": inconsistent_go_cells}


# --------------------------------------------------------------------------------- diagnostics
def check_v2(records, criteria):
    """Null region at the last pre-drift window. DIAGNOSTIC: never gates the P0 outcome."""
    frozen = _by_seed(records, "FROZEN")
    per_seed, n_empty = {}, 0
    for seed, rec in sorted(frozen.items()):
        last_pre = [s for s in rec["steps"] if s["t"] == rec["n_pre_windows"] - 1]
        if not last_pre:
            per_seed[seed] = {"status": "not_evaluated"}
            continue
        step = last_pre[0]
        empty = len(step["region"]) == 0
        n_empty += empty
        per_seed[seed] = {"status": "evaluated", "region_empty": empty, "region": step["region"],
                          "measurable": step["measurable"]}
    return {"pass": n_empty >= criteria.v2_min_seeds_empty, "n_seeds": len(frozen),
            "n_seeds_region_empty": n_empty, "required": criteria.v2_min_seeds_empty,
            "per_seed": per_seed}


def _share(table, c, key):
    row = table.get(c) if c in table else table.get(str(c), {})
    v = row.get(key, _NAN) if row else _NAN
    return _NAN if v is None else v


def ambiguity_flags(records_by_budget, statuses, eps_def):
    """Flag every class that generated a GO cell and whose D_sel or E rows are ambiguous at a share
    >= eps_def. Reporting only."""
    out = {}
    for b, recs in records_by_budget.items():
        by = _by_seed(recs, "REAL_ONLY")
        for seed, info in statuses[b]["per_seed"].items():
            rec = by[seed]
            amb = rec.get("ambiguity") or {}
            for c in info["go_classes"]:
                d_sel = _share(amb.get("d_sel", {}), c, "share")
                e = _share(amb.get("e_pooled", {}), c, "share")
                row = out.setdefault(c, {"seeds_with_go_cell": 0, "max_d_sel_share": _NAN,
                                         "max_e_share": _NAN, "possibly_ambiguity_driven": False})
                row["seeds_with_go_cell"] += 1
                for key, v in (("max_d_sel_share", d_sel), ("max_e_share", e)):
                    if v == v and (row[key] != row[key] or v > row[key]):
                        row[key] = v
                if (d_sel == d_sel and d_sel >= eps_def) or (e == e and e >= eps_def):
                    row["possibly_ambiguity_driven"] = True
    return {"threshold_eps_def": eps_def, "go_classes": out,
            "interpretation": "a GO class flagged possibly_ambiguity_driven may be intrinsically "
                              "unrepairable (contradictory feature vectors); report the GO with "
                              "that qualification. The flag never gates the outcome."}


def contamination_summary(records_by_budget):
    """Totals over seeds of learning-buffer rows duplicated in stable-evaluation partitions."""
    out = {}
    for b, recs in records_by_budget.items():
        per_cond = {}
        for r in recs:
            cont = r.get("contamination")
            if not cont:
                continue
            node = per_cond.setdefault(r["condition"], {})
            for part in ("real", "sel", "gate"):
                for dest, v in cont[part].items():
                    if dest == "n_rows":
                        continue
                    cell = node.setdefault(part, {}).setdefault(
                        dest, {"drift_pool_total": 0, "pre_pool_total": 0, "drift_pool_max_seed": 0})
                    cell["drift_pool_total"] += v["drift_pool"]
                    cell["pre_pool_total"] += v["pre_pool"]
                    cell["drift_pool_max_seed"] = max(cell["drift_pool_max_seed"], v["drift_pool"])
        out[b] = per_cond
    return out


# ------------------------------------------------------------------------------------ outcome
def scope_statement(statuses):
    """Mechanical budget-grid statement, e.g. 'NO_ROOM at B=100; B=25 unmeasurable'."""
    by = {s: sorted(b for b, v in statuses.items() if v == s) for s in STATUSES}
    parts = []
    if by["GO"]:
        parts.append("GO at B=" + ",".join(map(str, by["GO"])))
    if by["NO_ROOM"]:
        parts.append("NO_ROOM at B=" + ",".join(map(str, by["NO_ROOM"])))
    if by["UNMEASURABLE"]:
        parts.append("B=" + ",".join(map(str, by["UNMEASURABLE"])) + " unmeasurable")
    return "; ".join(parts)


def decide_outcome(valid, statuses):
    """INVALID > GO > NO_GO_NO_ROOM > INCONCLUSIVE_UNMEASURABLE. Each budget status is already
    exclusive, so no precedence among budgets is needed beyond this order."""
    if not valid:
        return "INVALID"
    values = list(statuses.values())
    if "GO" in values:
        return "GO"
    if "NO_ROOM" in values:
        return "NO_GO_NO_ROOM"
    return "INCONCLUSIVE_UNMEASURABLE"


def evaluate_p0(records_by_budget, manifest_audits, criteria, preregistered, prereg_problems=(),
                *, n_min, eps_def, nesting_audits=()):
    """Returns an ordered dict: validity, diagnostics, data_adequacy, h1."""
    all_records = [r for recs in records_by_budget.values() for r in recs]
    v4 = check_v4(records_by_budget, criteria, n_min)
    adequacy = {b: budget_status(recs, v4["repairable_set"], criteria, n_min)
                for b, recs in records_by_budget.items()}
    inconsistent = [dict(x, budget=b) for b, a in adequacy.items()
                    for x in a["inconsistent_go_cells"]]
    validity = {
        "v1_leakage_audit": check_v1(all_records, manifest_audits, nesting_audits),
        "v3_integrity": check_v3_integrity(records_by_budget, inconsistent),
        "v4_repairability": v4,
    }
    failed = [name for name, v in validity.items() if not v["pass"]]
    validity["all_pass"] = not failed
    validity["failed_checks"] = failed

    v2 = {b: check_v2(recs, criteria) for b, recs in records_by_budget.items()}
    v2_pass = all(x["pass"] for x in v2.values())
    diagnostics = {
        "v2_null_region": {"per_budget": v2, "pass": v2_pass, "gates_p0_outcome": False,
                           "p1_blocked": not v2_pass},
        "label_ambiguity": ambiguity_flags(records_by_budget, adequacy, eps_def),
        "cross_pool_contamination": contamination_summary(records_by_budget),
    }

    statuses = {b: a["status"] for b, a in adequacy.items()}
    data_adequacy = {"per_budget": adequacy, "statuses": statuses,
                     "insufficient_support_is_never_invalid": True}

    base = {"budget_statuses": statuses, "scope": scope_statement(statuses),
            "validity_all_pass": validity["all_pass"]}
    if not preregistered:
        h1 = {"status": "withheld_not_preregistered", "outcome": None,
              "problems": list(prereg_problems), **base}
    else:
        outcome = decide_outcome(validity["all_pass"], statuses)
        h1 = {"status": "evaluated", "outcome": outcome, **base}
        if outcome == "INVALID":
            h1["failed_checks"] = failed
    return {"validity": validity, "diagnostics": diagnostics, "data_adequacy": data_adequacy,
            "h1": h1}
