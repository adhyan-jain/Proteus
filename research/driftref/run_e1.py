"""E1 runner (see PREREG_E1.md, committed before this file existed).

One result file per seed: results/driftref/e1_seed{s}.json with the raw 0/1 fire arrays, so the
analysis (analyze_e1.py) can bootstrap without rerunning anything.

CPU sklearn RandomForest, like the repo's other P-line experiments; there is no neural training
in E1 (CLAUDE.md rule 1 concerns neural-net training; flagged in the report).
"""
import proteus.config  # noqa: F401 -- must import before numpy/sklearn

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

from proteus.drift import detect_drift

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "results" / "cache" / "cicids2017_v1.npz"
OUT = ROOT / "results" / "driftref"
PRE_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday")

N_FIT = 200_000          # model-fit subsample (PREREG: RAM limit)
N_BUF_REF, N_BUF_RECENT = 20_000, 5_000
N_WIN = 300
N_HOLD_REF = 20_000      # size of HOLD reference sample (unspecified in PREREG; recorded)
N_IN_SAMPLE_REF = 50_000 # closed_loop_full.py uses X_train_init[:50000]
N_DRAWS = 200            # C5 reference draws
PROFILES = {
    "LOOP": dict(W=1000, alpha=0.05),
    "DAEMON": dict(W=100, alpha=0.01),
}
N_FRIDAY_WIN = 100


def conf(model, X, chunk=100_000):
    out = np.empty(len(X), dtype=np.float32)
    for s in range(0, len(X), chunk):
        out[s:s + chunk] = model.predict_proba(X[s:s + chunk]).max(axis=1)
    return out


def fires(win_conf, ref_conf, alpha):
    """win_conf: (n_win, W). Returns list of 0/1 from proteus.drift.detect_drift."""
    return [int(detect_drift(w, ref_conf, alpha=alpha)["fired"]) for w in win_conf]


def role(group, seed):
    salt = np.uint64((int(seed) * 0x9E3779B97F4A7C15) % (1 << 64))
    return ((np.asarray(group, dtype=np.uint64) ^ salt) >> np.uint64(13)) % np.uint64(10)
    # 0-4 TRAIN, 5 HOLD, 6-9 STREAM


def rf(seed, depth=None):
    return RandomForestClassifier(n_estimators=100, max_depth=depth, random_state=seed, n_jobs=4)


def run_seed(seed, z):
    t0 = time.time()
    X, y, day, group = z["X"], z["y"], z["day"], z["group"]
    mt = np.flatnonzero(np.isin(day, PRE_DAYS))
    fri = np.flatnonzero(day == "Friday")
    r = role(group[mt], seed)
    train, hold, stream = mt[r <= 4], mt[r == 5], mt[r >= 6]
    rng = np.random.default_rng([seed, 11])

    s1 = rng.choice(train, N_FIT, replace=False)
    s2 = rng.choice(train, N_FIT, replace=False)
    stream = stream[rng.permutation(len(stream))]
    adapt_pool, stream = stream[:N_BUF_RECENT], stream[N_BUF_RECENT:]
    buf_ref = rng.choice(train, N_BUF_REF, replace=False)
    buf_idx = np.concatenate([buf_ref, adapt_pool])

    models = {
        "A": rf(seed).fit(X[s1], y[s1]),
        "A2": rf(seed + 1000).fit(X[s2], y[s2]),
        "B_loop": rf(42).fit(X[buf_idx], y[buf_idx]),
        "B_daemon": rf(42, depth=15).fit(X[buf_idx], y[buf_idx]),
    }
    hold_ref = rng.choice(hold, min(N_HOLD_REF, len(hold)), replace=False)
    quality = {}
    for k, m in models.items():
        p = m.predict(X[hold_ref])
        quality[k] = {"acc": float((p == y[hold_ref]).mean()),
                      "macro_f1": float(f1_score(y[hold_ref], p, average="macro", zero_division=0)),
                      "mean_conf_hold": float(conf(m, X[hold_ref]).mean())}
    print(f"[seed {seed}] fitted {len(models)} models in {time.time()-t0:.0f}s", flush=True)

    # row pools (all disjoint inside STREAM)
    n_loop = N_WIN * PROFILES["LOOP"]["W"]
    n_dmn = N_WIN * PROFILES["DAEMON"]["W"]
    loop_rows = stream[:n_loop]
    dmn_rows = stream[n_loop:n_loop + n_dmn]
    draw_rows = stream[n_loop + n_dmn:n_loop + n_dmn + N_DRAWS * 30]
    fri_rows = rng.choice(fri, N_FRIDAY_WIN * 1000, replace=False)

    res = {"seed": seed,
           "sizes": {"train": int(len(train)), "hold": int(len(hold)), "stream": int(len(stream) + N_BUF_RECENT)},
           "quality": quality, "profiles": {}}
    cache = {}
    for name, m in models.items():
        cache[name] = {
            "loop": conf(m, X[loop_rows]).reshape(N_WIN, -1),
            "dmn": conf(m, X[dmn_rows]).reshape(N_WIN, -1),
            "hold": conf(m, X[hold_ref]),
        }
    A = models["A"]
    cache["A"]["draw"] = conf(A, X[draw_rows]).reshape(N_DRAWS, 30)
    cache["A"]["insample"] = conf(A, X[s1[:N_IN_SAMPLE_REF]])
    cache["A"]["fri_loop"] = conf(A, X[fri_rows]).reshape(N_FRIDAY_WIN, -1)
    cache["A"]["fri_dmn"] = conf(A, X[fri_rows[:N_FRIDAY_WIN * 100]]).reshape(N_FRIDAY_WIN, -1)
    print(f"[seed {seed}] confidences done {time.time()-t0:.0f}s", flush=True)

    swapped = {"LOOP": ["A2", "B_loop"], "DAEMON": ["A2", "B_daemon"]}
    ref_hold_A = cache["A"]["hold"]
    # ---- LOOP
    a = PROFILES["LOOP"]["alpha"]; L = {}
    L["C0_validity"] = fires(cache["A"]["loop"], ref_hold_A, a)
    L["C1_noswap_system"] = fires(cache["A"]["loop"], cache["A"]["insample"], a)
    for x in swapped["LOOP"]:
        L[f"C2_stale_{x}"] = fires(cache[x]["loop"], cache["A"]["insample"], a)
        L[f"C2h_stale_holdref_{x}"] = fires(cache[x]["loop"], ref_hold_A, a)  # stale but unbiased ref
        L[f"C3_fresh_{x}"] = fires(cache[x]["loop"], cache[x]["hold"], a)
    L["C4_positive"] = fires(cache["A"]["fri_loop"], ref_hold_A, a)
    res["profiles"]["LOOP"] = L
    # ---- DAEMON (draw-level units: [draw][window])
    a = PROFILES["DAEMON"]["alpha"]; D = {}
    D["C0_validity"] = fires(cache["A"]["dmn"], ref_hold_A, a)
    D["C4_positive"] = fires(cache["A"]["fri_dmn"], ref_hold_A, a)
    for x in swapped["DAEMON"]:
        D[f"C3_fresh_{x}"] = fires(cache[x]["dmn"], cache[x]["hold"], a)
    c1, c2 = [], {x: [] for x in swapped["DAEMON"]}
    for d in range(N_DRAWS):
        ref = cache["A"]["draw"][d]
        c1.append(fires(cache["A"]["dmn"], ref, a))
        for x in swapped["DAEMON"]:
            c2[x].append(fires(cache[x]["dmn"], ref, a))
    D["C1_noswap_system_by_draw"] = c1
    for x in swapped["DAEMON"]:
        D[f"C2_stale_by_draw_{x}"] = c2[x]
    res["profiles"]["DAEMON"] = D
    res["elapsed_s"] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"e1_seed{seed}.json").write_text(json.dumps(res))
    print(f"[seed {seed}] done in {res['elapsed_s']}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    a = ap.parse_args()
    z = np.load(CACHE, allow_pickle=False)
    z = {k: z[k] for k in ("X", "y", "day", "group")}
    for s in a.seeds:
        if (OUT / f"e1_seed{s}.json").exists():
            print(f"seed {s} exists, skipping"); continue
        run_seed(s, z)
