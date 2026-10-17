"""E1 analysis exactly as fixed in PREREG_E1.md: two-level cluster bootstrap (seeds, then windows
or reference draws within seed), 5000 reps, percentile 95% CI. Verdicts H1/H2/H3/H5."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "driftref"
ALPHA = {"LOOP": 0.05, "DAEMON": 0.01}
B = 5000


def load():
    return [json.loads(p.read_text()) for p in sorted(RES.glob("e1_seed*.json"))]


def units(seed_res, prof, cond):
    """Per-seed 1-D array of cluster values. LOOP: window 0/1. DAEMON *_by_draw: per-draw FAR."""
    v = seed_res["profiles"][prof][cond]
    a = np.asarray(v, dtype=float)
    return a.mean(axis=1) if a.ndim == 2 else a


def boot(per_seed, rng):
    """Two-level bootstrap of the mean of cluster values. Returns point, lo, hi."""
    n = len(per_seed)
    point = float(np.mean([u.mean() for u in per_seed]))
    ms = np.array([u.mean() for u in per_seed])
    out = np.empty(B)
    for b in range(B):
        si = rng.integers(0, n, n)
        vals = []
        for i in si:
            u = per_seed[i]
            vals.append(u[rng.integers(0, len(u), len(u))].mean())
        out[b] = np.mean(vals)
    return point, float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def main():
    runs = load()
    rng = np.random.default_rng(20261017)
    rows = {}
    conds = {p: [c for c in runs[0]["profiles"][p]] for p in ALPHA}
    for prof in ALPHA:
        for c in conds[prof]:
            rows[(prof, c)] = boot([units(r, prof, c) for r in runs], rng)
    # quality table
    qual = {m: {k: float(np.mean([r["quality"][m][k] for r in runs])) for k in ("acc", "macro_f1", "mean_conf_hold")}
            for m in runs[0]["quality"]}
    # verdicts
    v = {"n_seeds": len(runs)}
    v["H2_validity"] = {p: {"C0": rows[(p, "C0_validity")], "alpha": ALPHA[p],
                            "contains_alpha": rows[(p, "C0_validity")][1] <= ALPHA[p] <= rows[(p, "C0_validity")][2],
                            "C4_far": rows[(p, "C4_positive")][0]} for p in ALPHA}
    v["H2_pass"] = all(x["contains_alpha"] and x["C4_far"] >= 0.95 for x in v["H2_validity"].values())
    swapped = {"LOOP": ["A2", "B_loop"], "DAEMON": ["A2", "B_daemon"]}
    h1, h3 = {}, {}
    for p in ALPHA:
        for x in swapped[p]:
            key = f"C2_stale_{x}" if p == "LOOP" else f"C2_stale_by_draw_{x}"
            lo = rows[(p, key)]
            h1[f"{p}/{x}"] = {"far": lo, "violates": lo[1] > 2 * ALPHA[p]}
            f = rows[(p, f"C3_fresh_{x}")]
            h3[f"{p}/{x}"] = {"far": f, "repaired": f[2] <= ALPHA[p] + 0.02}
    v["H1"], v["H3"] = h1, h3
    v["H1_pass"] = any(x["violates"] for x in h1.values())
    v["H3_pass"] = all(x["repaired"] for x in h3.values())
    # H5 reference lottery (daemon): share of draws with conditional FAR > 2*alpha, pooled over seeds
    for cond in ("C1_noswap_system_by_draw", "C2_stale_by_draw_A2", "C2_stale_by_draw_B_daemon"):
        d = np.concatenate([units(r, "DAEMON", cond) for r in runs])
        v[f"H5_{cond}"] = {"share_draws_far_gt_2alpha": float((d > 2 * ALPHA["DAEMON"]).mean()),
                           "share_draws_far_gt_0.5": float((d > 0.5).mean()),
                           "median_far": float(np.median(d)), "p90_far": float(np.percentile(d, 90))}
    out = {"verdicts": v, "table": {f"{p}/{c}": rows[(p, c)] for (p, c) in rows}, "quality_mean": qual}
    (RES / "e1_analysis.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
