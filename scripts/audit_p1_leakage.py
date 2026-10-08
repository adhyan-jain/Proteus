"""Independent leakage audit of the P1 campaign (hostile-review item), recomputed from raw features.

    .venv/bin/python scripts/audit_p1_leakage.py [--seeds 0 1 ... 9]

It does NOT reuse the runner's `Auditor`. For each seed it rebuilds the manifest, replays the label
stream into the learning buffers, re-hashes the raw float32 feature bytes of every row it touches
(blake2b, as in the cache) and checks, per temporal pool:
  * no learning row (D_ref, D_real, D_sel, D_gate, S_sel, S_gate, canary labels) shares a feature
    vector with any reporting row (E_t of every window, S_report) or the drift-detector reference
    (S_cal) of the SAME pool; cross-pool duplicates are counted, not failed (legal, spec E5);
  * the cached group ids equal the re-computed hashes;
  * the generator input set is exactly the target class's D_real rows (spy generator);
  * the manifest digest equals the P0 digest for seeds 0-4.
Writes results/p1_leakage_audit.json.
"""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import proteus.config  # noqa: F401,E402
from proteus.intervention.cache import CACHE_PATH, hash_rows, load_cache  # noqa: E402
from proteus.intervention.conditions import DecisionContext  # noqa: E402
from proteus.intervention.controller import DataOperator  # noqa: E402
from proteus.intervention.generators import SMOTEGenerator  # noqa: E402
from proteus.intervention.learner import CandidateBuilder  # noqa: E402
from proteus.intervention.p0 import TrackedState  # noqa: E402
from proteus.intervention.params import InterventionParams  # noqa: E402
from proteus.intervention.protocol import SCENARIOS, StreamReplay, build_partitions  # noqa: E402
from proteus.intervention.provenance import git_state, utc_now_iso  # noqa: E402
from proteus.intervention.serialize import write_json  # noqa: E402


def groups_of(data, idx):
    return hash_rows(data.X[np.asarray(idx, dtype=np.int64)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    args = ap.parse_args()
    data = load_cache(CACHE_PATH)
    cfg = replace(SCENARIOS["S1"], budget=100)
    params = InterventionParams()
    pool = np.zeros(len(data.day), dtype=np.int8)
    pool[np.isin(data.day, cfg.pre_days)] = 1
    pool[np.isin(data.day, cfg.drift_days)] = 2
    p0 = json.loads((ROOT / "results" / "intervention_p0_S1_B100.json").read_text())["manifests"]
    results = []
    for seed in args.seeds:
        m = build_partitions(data, cfg, seed)
        st = TrackedState(data, m)
        for step in StreamReplay(m):
            st.ingest(step)
        prov = st.provenance()
        # --- re-hash everything we compare ------------------------------------------------
        forbidden_rows = np.concatenate([w.e_idx for w in m.windows] + [m.s_report_idx, m.s_cal_idx])
        learn = {k: np.asarray(v, dtype=np.int64) for k, v in prov.items()}
        learn["canary_labels"] = np.concatenate([w.l_idx for w in m.windows])
        cached_equal = True
        h_forb = groups_of(data, forbidden_rows)
        cached_equal &= bool(np.array_equal(h_forb, data.group[forbidden_rows]))
        per_set, violations, cross = {}, 0, 0
        for name, rows in learn.items():
            h = groups_of(data, rows)
            cached_equal &= bool(np.array_equal(h, data.group[rows]))
            same = cross_n = 0
            for p in (1, 2):
                mask_l, mask_f = pool[rows] == p, pool[forbidden_rows] == p
                same += int(np.isin(h[mask_l], h_forb[mask_f]).sum())
                other = 3 - p
                cross_n += int(np.isin(h[mask_l], h_forb[pool[forbidden_rows] == other]).sum())
            row_overlap = int(np.isin(rows, forbidden_rows).sum())
            per_set[name] = {"n_rows": int(len(rows)), "same_pool_vector_overlap_with_E_Sreport_Scal": same,
                             "row_overlap": row_overlap, "cross_pool_duplicates_informational": cross_n}
            violations += same + row_overlap
            cross += cross_n
        # --- generator input set ---------------------------------------------------------------
        view = st.view()
        seen = {}

        class Spy(SMOTEGenerator):
            def fit(self, X_c, c, rng):
                seen[int(c)] = np.asarray(X_c, dtype=np.float32).copy()
                return super().fit(X_c, c, rng)

        op = DataOperator("SPY", lambda c, v, p: Spy())
        classes = tuple(int(c) for c in np.unique(view.real_y) if (view.real_y == c).sum() >= params.n_min)
        op.prepare(view, CandidateBuilder(params, seed), None, classes, params,
                   DecisionContext(t=13, seed=seed, params=params))
        gen_ok = all(np.array_equal(seen[c], view.real_X[view.real_y == c]) for c in classes)
        real_hashes = set(groups_of(data, learn["real"]).tolist())
        gen_subset = all(set(hash_rows(seen[c]).tolist()) <= real_hashes for c in classes)
        match = (p0[str(seed)]["digest"] == m.digest()) if str(seed) in p0 else None
        results.append({"seed": seed, "violations": violations, "cached_group_ids_equal_recomputed": cached_equal,
                        "generator_inputs_are_exactly_target_class_D_real_rows": bool(gen_ok and gen_subset),
                        "n_generator_classes_checked": len(classes), "manifest_equals_p0": match,
                        "sets": per_set, "cross_pool_duplicates_total": cross})
        print(f"seed {seed}: violations={violations} cache_ok={cached_equal} gen_ok={gen_ok and gen_subset} p0={match}")
    doc = {"kind": "p1_leakage_audit", **git_state(), "audited_utc": utc_now_iso(),
           "all_pass": all(r["violations"] == 0 and r["cached_group_ids_equal_recomputed"]
                           and r["generator_inputs_are_exactly_target_class_D_real_rows"]
                           and r["manifest_equals_p0"] in (None, True) for r in results),
           "seeds": results}
    write_json(ROOT / "results" / "p1_leakage_audit.json", doc)
    print("ALL PASS" if doc["all_pass"] else "FAIL")
    return 0 if doc["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
