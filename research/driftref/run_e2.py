"""E2 runner (see PREREG_E2.md, committed before this file existed).

Families: RF-100 (sklearn, CPU) and two PyTorch MLPs (CUDA required, CLAUDE.md rule 1).
One result file per seed: results/driftref/e2_seed{s}.json (raw 0/1 fire arrays).
"""
import proteus.config  # noqa: F401 -- must import before numpy/sklearn/torch

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

from proteus.drift import detect_drift

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "results" / "cache" / "cicids2017_v1.npz"
OUT = ROOT / "results" / "driftref"
PRE_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday")
N_REF_MODEL = 200_000
SIZES = (5_000, 25_000, 100_000, 200_000)
FAMILIES = ("RF", "MLP64", "MLP512")
W, N_WIN, ALPHA, N_HOLD_REF, N_FRI_WIN = 1000, 300, 0.05, 20_000, 100

if not torch.cuda.is_available():
    raise RuntimeError("CUDA not available -- GPU-only training rule (CLAUDE.md rule 1).")
DEV = "cuda"


def role(group, seed):
    salt = np.uint64((int(seed) * 0x9E3779B97F4A7C15) % (1 << 64))
    return ((np.asarray(group, dtype=np.uint64) ^ salt) >> np.uint64(13)) % np.uint64(10)


def prep(X):
    return np.clip(np.sign(X) * np.log1p(np.abs(X)), -50, 50).astype(np.float32)


class Model:
    """Uniform interface: pred_conf(raw X) -> (predicted class, max-probability confidence)."""

    def __init__(self, family, X, y, seed):
        self.family = family
        if family == "RF":
            self.m = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=4).fit(X, y)
            return
        width = {"MLP64": 64, "MLP512": 512}[family]
        torch.manual_seed(seed)
        Z = prep(X)
        self.mu, self.sd = Z.mean(0), Z.std(0) + 1e-6
        Zt = torch.from_numpy(np.clip((Z - self.mu) / self.sd, -10, 10)).to(DEV)
        yt = torch.from_numpy(y.astype(np.int64)).to(DEV)
        self.net = nn.Sequential(nn.Linear(Z.shape[1], width), nn.ReLU(), nn.Linear(width, width),
                                 nn.ReLU(), nn.Linear(width, 25)).to(DEV)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        g = torch.Generator(device=DEV); g.manual_seed(seed)
        for _ in range(20):
            perm = torch.randperm(len(Zt), device=DEV, generator=g)
            for s in range(0, len(Zt), 512):
                b = perm[s:s + 512]
                opt.zero_grad()
                nn.functional.cross_entropy(self.net(Zt[b]), yt[b]).backward()
                opt.step()
        self.net.eval()

    def pred_conf(self, X, chunk=100_000):
        P = np.empty(len(X), dtype=np.int64); C = np.empty(len(X), dtype=np.float32)
        for s in range(0, len(X), chunk):
            xb = X[s:s + chunk]
            if self.family == "RF":
                pr = self.m.predict_proba(xb)
                P[s:s + chunk] = self.m.classes_[pr.argmax(1)]; C[s:s + chunk] = pr.max(1)
            else:
                z = torch.from_numpy(np.clip((prep(xb) - self.mu) / self.sd, -10, 10)).to(DEV)
                with torch.no_grad():
                    pr = torch.softmax(self.net(z), 1)
                mx, idx = pr.max(1)
                C[s:s + chunk], P[s:s + chunk] = mx.cpu().numpy(), idx.cpu().numpy()
        return P, C


def fires(win_conf, ref_conf):
    return [int(detect_drift(w, ref_conf, alpha=ALPHA)["fired"]) for w in win_conf]


def run_seed(seed, z):
    t0 = time.time()
    X, y, day, group = z["X"], z["y"], z["day"], z["group"]
    mt = np.flatnonzero(np.isin(day, PRE_DAYS)); fri = np.flatnonzero(day == "Friday")
    r = role(group[mt], seed)
    train, hold, stream = mt[r <= 4], mt[r == 5], mt[r >= 6]
    rng = np.random.default_rng([seed, 22])
    stream = stream[rng.permutation(len(stream))]
    win_rows = stream[:N_WIN * W]
    hold_ref = rng.choice(hold, N_HOLD_REF, replace=False)
    fri_rows = rng.choice(fri, N_FRI_WIN * W, replace=False)
    ref_idx = rng.choice(train, N_REF_MODEL, replace=False)
    srv_idx = {n: rng.choice(train, n, replace=False) for n in SIZES}

    res = {"seed": seed, "cells": {}, "positive": {}}
    for fam in FAMILIES:
        refm = Model(fam, X[ref_idx], y[ref_idx], seed)
        _, ref_hold_conf = refm.pred_conf(X[hold_ref])
        res["cells"][fam] = {}
        for n in SIZES:
            sm = Model(fam, X[srv_idx[n]], y[srv_idx[n]], seed + 1000 + n)
            p, c_hold = sm.pred_conf(X[hold_ref])
            _, c_win = sm.pred_conf(X[win_rows])
            c_win = c_win.reshape(N_WIN, W)
            res["cells"][fam][str(n)] = {
                "quality": {"acc": float((p == y[hold_ref]).mean()),
                            "macro_f1": float(f1_score(y[hold_ref], p, average="macro", zero_division=0)),
                            "mean_conf": float(c_hold.mean()),
                            "ref_mean_conf": float(ref_hold_conf.mean())},
                "stale": fires(c_win, ref_hold_conf),
                "fresh": fires(c_win, c_hold),
            }
            if n == N_REF_MODEL:
                _, c_fri = sm.pred_conf(X[fri_rows])
                res["positive"][fam] = fires(c_fri.reshape(N_FRI_WIN, W), c_hold)
            del sm
        print(f"[seed {seed}] {fam} done {time.time()-t0:.0f}s", flush=True)
        del refm
        torch.cuda.empty_cache()
    res["elapsed_s"] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"e2_seed{seed}.json").write_text(json.dumps(res))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, nargs="+", required=True)
    a = ap.parse_args()
    z = np.load(CACHE, allow_pickle=False)
    z = {k: z[k] for k in ("X", "y", "day", "group")}
    for s in a.seeds:
        if (OUT / f"e2_seed{s}.json").exists():
            print(f"seed {s} exists, skipping"); continue
        run_seed(s, z)
