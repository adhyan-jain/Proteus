"""Hostile-review sensitivity checks on the finished P1 campaign (read-only on the result files).

    .venv/bin/python scripts/audit_p1_sensitivity.py

Writes results/p1_audit_sensitivity.json with: parameter/threshold continuity with the frozen P0,
seed-group split (0-4 share P0's manifests and R was derived on them; 5-9 are independent of R),
leave-one-seed-out ranges, and alternative endpoints that test the post-hoc restriction to R.
Exploratory: nothing here feeds the preregistered verdict.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import proteus.config  # noqa: F401,E402
from proteus.intervention.analyze_p1 import fin, load_seed_files, mean, p0_reference, run_metrics  # noqa: E402
from proteus.intervention.metrics import t_ci  # noqa: E402
from proteus.intervention.params import InterventionParams  # noqa: E402
from proteus.intervention.provenance import git_state, utc_now_iso  # noqa: E402
from proteus.intervention.serialize import from_jsonable, loads_strict, write_json  # noqa: E402

docs = load_seed_files(ROOT / "results" / "p1")
seeds = sorted(docs)
p0s, _ = p0_reference(ROOT / "results")
summ = from_jsonable(loads_strict((ROOT / "results" / "intervention_p1_S1_B100_summary.json").read_text()))
names = summ["class_names"]
params = InterventionParams()
k = len(names)
R = sorted(docs[seeds[0]]["repairable_set_R"])
ARMS = ["REAL_ONLY", "CTRL-SMOTE", "FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE"]


def table(Rset):
    out = {}
    for a in ARMS:
        out[a] = {}
        for s in seeds:
            run = next(r for r in docs[s]["runs"] if r["arm"] == a)
            out[a][s] = run_metrics(run, Rset, params.s_min, k, docs[s]["base_stats"], params)
    return out


def ci(xs):
    c = t_ci(fin(xs))
    return {kk: (None if v != v else v) for kk, v in c.items()}


# 1. continuity of parameters with the frozen P0 ----------------------------------------------------
cont = {"p1_params_digest": sorted({d["params_digest"] for d in docs.values()}),
        "p0_params_digest": p0s["params_digest"],
        "p1_params_equal_p0": sorted({d["params_digest"] for d in docs.values()}) == [p0s["params_digest"]],
        "p1_rules_hash_in_every_seed_file_equals_current": len({d["p1_rules_sha256"] for d in docs.values()}) == 1,
        "p0_rules_hash": p0s["spec_rules_sha256"],
        "frozen_thresholds": {f: getattr(params, f) for f in ("eps_def", "eps_s", "eps_fpr", "eta", "eps_ni", "alpha", "k_max")},
        "code_hash_variants_across_seed_files": len({json.dumps(d["code_files_sha256"], sort_keys=True) for d in docs.values()})}

# 2. endpoint variants (tests the post-hoc restriction to R) ----------------------------------------
variants = {"R=preregistered {Bot,DDoS,PortScan}": R,
            "R'={DDoS,PortScan} (drop Bot: tiny support)": [c for c in R if names[c] != "Bot"],
            "R''={PortScan} (the only GO class)": [names.index("PortScan")]}
endpoints = {}
for label, Rset in variants.items():
    t = table(Rset)
    endpoints[label] = {a: {"deployed": ci([t[a][s]["r_recovery"] for s in seeds]),
                            "candidate(shadow)": ci([t[a][s]["shadow_candidate"] for s in seeds]),
                            "deployed_minus_real_only": ci([t[a][s]["r_recovery"] - t["REAL_ONLY"][s]["r_recovery"] for s in seeds]),
                            "candidate_minus_real_only": ci([t[a][s]["shadow_candidate"] - t["REAL_ONLY"][s]["shadow_candidate"] for s in seeds])}
                        for a in ARMS}
base_t = table(R)

# 3. seed groups and leave-one-seed-out --------------------------------------------------------------
groups = {"seeds_0_4 (P0 manifests; R derived on them)": [0, 1, 2, 3, 4],
          "seeds_5_9 (independent of R's derivation)": [5, 6, 7, 8, 9]}
by_group = {g: {a: {"deployed_mean": mean([base_t[a][s]["r_recovery"] for s in ss]),
                    "candidate_mean": mean([base_t[a][s]["shadow_candidate"] for s in ss]),
                    "deployed_minus_real_only_mean": mean([base_t[a][s]["r_recovery"] - base_t["REAL_ONLY"][s]["r_recovery"] for s in ss]),
                    "candidate_minus_real_only_mean": mean([base_t[a][s]["shadow_candidate"] - base_t["REAL_ONLY"][s]["shadow_candidate"] for s in ss])}
                for a in ARMS} for g, ss in groups.items()}
loo = {}
for a in ARMS:
    if a == "REAL_ONLY":
        continue
    cand = [mean([base_t[a][s]["shadow_candidate"] - base_t["REAL_ONLY"][s]["shadow_candidate"] for s in seeds if s != d]) for d in seeds]
    dep = [mean([base_t[a][s]["r_recovery"] - base_t["REAL_ONLY"][s]["r_recovery"] for s in seeds if s != d]) for d in seeds]
    loo[a] = {"candidate_gain_min": min(cand), "candidate_gain_max": max(cand),
              "deployed_gain_min": min(dep), "deployed_gain_max": max(dep)}
seed_sd = {a: {"deployed_sd": float(np.std([base_t[a][s]["r_recovery"] for s in seeds], ddof=1)),
               "candidate_sd": float(np.std([base_t[a][s]["shadow_candidate"] for s in seeds], ddof=1))} for a in ("REAL_ONLY", "FIXED-SMOTE-4")}
never = [s for s in seeds if base_t["REAL_ONLY"][s]["r_recovery"] == 0]

doc = {"kind": "p1_audit_sensitivity", **git_state(), "audited_utc": utc_now_iso(),
       "continuity_with_frozen_p0": cont, "endpoint_variants": endpoints, "seed_groups": by_group,
       "leave_one_seed_out": loo, "seed_sd": seed_sd, "seeds_where_real_only_never_deployed": never,
       "note": "exploratory; the preregistered verdict is unchanged by any of these"}
write_json(ROOT / "results" / "p1_audit_sensitivity.json", doc)
print(json.dumps({"continuity": cont, "never": never, "loo": loo}, indent=1, default=str)[:2500])
for g, v in by_group.items():
    print(g, {a: (round(x["deployed_mean"], 3), round(x["candidate_mean"], 3)) for a, x in v.items() if a in ("REAL_ONLY", "FIXED-SMOTE-4")})
for lab, v in endpoints.items():
    print(lab, "| real-only deployed", round(v["REAL_ONLY"]["deployed"]["mean"], 3), "candidate", round(v["REAL_ONLY"]["candidate(shadow)"]["mean"], 3),
          "| fixed4 cand gain", round(v["FIXED-SMOTE-4"]["candidate_minus_real_only"]["mean"], 4), "dep gain", round(v["FIXED-SMOTE-4"]["deployed_minus_real_only"]["mean"], 4))
