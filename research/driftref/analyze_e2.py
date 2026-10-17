"""E2 analysis exactly as fixed in PREREG_E2.md: two-level cluster bootstrap (seeds, then windows),
5000 reps, percentile 95%; verdicts H6-H9."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "driftref"
ALPHA, B = 0.05, 5000
FAMS, SIZES = ("RF", "MLP64", "MLP512"), ("5000", "25000", "100000", "200000")


def boot(per_seed, rng):
    n = len(per_seed)
    point = float(np.mean([u.mean() for u in per_seed]))
    out = np.empty(B)
    for b in range(B):
        si = rng.integers(0, n, n)
        out[b] = np.mean([per_seed[i][rng.integers(0, len(per_seed[i]), len(per_seed[i]))].mean() for i in si])
    return point, float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def main():
    runs = [json.loads(p.read_text()) for p in sorted(RES.glob("e2_seed*.json"))]
    rng = np.random.default_rng(20261018)
    tab, qual = {}, {}
    for f in FAMS:
        for n in SIZES:
            for kind in ("stale", "fresh"):
                tab[f"{f}/{n}/{kind}"] = boot([np.asarray(r["cells"][f][n][kind], float) for r in runs], rng)
            qual[f"{f}/{n}"] = {k: float(np.mean([r["cells"][f][n]["quality"][k] for r in runs]))
                                for k in ("acc", "macro_f1", "mean_conf", "ref_mean_conf")}
    pos = {f: boot([np.asarray(r["positive"][f], float) for r in runs], rng) for f in FAMS}
    v = {"n_seeds": len(runs)}
    v["H6_per_family"] = {f: {"far": tab[f"{f}/25000/stale"], "violates": tab[f"{f}/25000/stale"][1] > 2 * ALPHA} for f in FAMS}
    v["H6_pass"] = sum(x["violates"] for x in v["H6_per_family"].values()) >= 2
    v["H7_per_family"] = {f: {"far": tab[f"{f}/200000/stale"], "valid": tab[f"{f}/200000/stale"][2] <= ALPHA + 0.02} for f in FAMS}
    v["H7_pass"] = all(x["valid"] for x in v["H7_per_family"].values())
    v["H8_per_cell"] = {k: {"far": t, "repaired": t[2] <= ALPHA + 0.02} for k, t in tab.items() if k.endswith("/fresh")}
    v["H8_pass"] = all(x["repaired"] for x in v["H8_per_cell"].values())
    v["H9_per_family"] = {f: {"far": pos[f], "sensitive": pos[f][0] >= 0.95} for f in FAMS}
    v["H9_pass"] = all(x["sensitive"] for x in v["H9_per_family"].values())
    out = {"verdicts": v, "table": tab, "quality_mean": qual, "positive": pos}
    (RES / "e2_analysis.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(v, indent=1))
    print("--- dose response (stale FAR, EXPLORATORY) ---")
    for f in FAMS:
        print(f, [(n, round(tab[f"{f}/{n}/stale"][0], 3), round(qual[f"{f}/{n}"]["mean_conf"], 4), round(qual[f"{f}/{n}"]["acc"], 4)) for n in SIZES],
              "ref_conf", round(qual[f"{f}/200000"]["ref_mean_conf"], 4))


if __name__ == "__main__":
    main()
