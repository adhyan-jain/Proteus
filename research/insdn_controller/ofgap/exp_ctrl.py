"""Controller-native detection on real InSDN OpenFlow control-channel telemetry.

Window-level normal-vs-attack classification, evaluated so that no capture file is in both train
and test (grouped CV by capture, reshuffled per seed) and with leave-one-attack-class-out (LOCO).
Baselines: PacketIn-rate threshold and source-IP-entropy threshold (thresholds fit on train folds).
Ablations: PacketIn-only features, flow-stats-only features. GPU MLP with 4-window history.
10 seeds, mean +/- 95% t-CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import FEATS  # noqa: E402

assert torch.cuda.is_available(), "CUDA required (CLAUDE.md rule 1)"
DEV = torch.device("cuda")
H = 4  # history windows
GROUPS = {
    "all": list(range(len(FEATS))),
    "packet_in_only": [i for i, f in enumerate(FEATS) if not f.startswith("st_") and f not in ("n_stats",)],
    "stats_only": [i for i, f in enumerate(FEATS) if f.startswith("st_") or f == "n_stats"],
}


def load(d: Path, W: float):
    meta = json.loads((d / "meta.json").read_text())
    caps = []
    for cid, m in sorted(meta.items()):
        X = np.load(d / f"{cid}_W{W:g}.npy")
        if len(X) == 0:
            continue
        caps.append(dict(id=cid, label=m["label"], X=X, y=int(m["label"] != "normal")))
    return caps


def with_history(X):
    Z = np.log1p(np.maximum(X, 0))
    pads = [np.vstack([np.zeros((min(k, len(Z)), Z.shape[1]), Z.dtype), Z[:max(len(Z) - k, 0)]]) for k in range(H)]
    return np.hstack(pads).astype(np.float32)


def cols_with_history(idx):
    nf = len(FEATS)
    return [k * nf + i for k in range(H) for i in idx]


def fit(X, y, seed, epochs=40):
    torch.manual_seed(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    m = nn.Sequential(nn.Linear(X.shape[1], 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 32), nn.ReLU(),
                      nn.Linear(32, 2)).to(DEV)
    w = torch.tensor([len(y) / (2 * max((y == c).sum(), 1)) for c in (0, 1)], dtype=torch.float32, device=DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-3)
    Xt, yt = torch.tensor((X - mu) / sd, device=DEV), torch.tensor(y, device=DEV)
    g = torch.Generator(device=DEV).manual_seed(seed)
    m.train()
    for _ in range(epochs):
        perm = torch.randperm(len(Xt), device=DEV, generator=g)
        for b in range(0, len(perm), 256):
            i = perm[b:b + 256]
            opt.zero_grad()
            nn.functional.cross_entropy(m(Xt[i]), yt[i], weight=w).backward()
            opt.step()
    m.eval()

    @torch.no_grad()
    def predict(Xq):
        return torch.softmax(m(torch.tensor((Xq - mu) / sd, device=DEV)), 1)[:, 1].cpu().numpy()
    return predict


def thr_fit(v, y):
    """Best balanced-accuracy threshold on a single score (train folds only)."""
    cand = np.unique(np.quantile(v, np.linspace(0, 1, 201)))
    best, bt = -1, cand[0]
    for t in cand:
        p = v >= t
        b = (p[y == 1].mean() if (y == 1).any() else 0) / 2 + ((~p)[y == 0].mean() if (y == 0).any() else 0) / 2
        if b > best:
            best, bt = b, t
    return bt


def met(y, yhat):
    rec = yhat[y == 1].mean() if (y == 1).any() else np.nan
    fpr = yhat[y == 0].mean() if (y == 0).any() else np.nan
    return dict(recall=float(rec), fpr=float(fpr), bacc=float((rec + 1 - fpr) / 2))


def ci(v):
    v = np.asarray([x for x in v if not np.isnan(x)], float)
    h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
    return dict(mean=float(v.mean()) if len(v) else float("nan"), ci95=float(h), n=int(len(v)))


def run_split(train, test, seed, out):
    Xtr = np.vstack([with_history(c["X"]) for c in train])
    ytr = np.concatenate([np.full(len(c["X"]), c["y"]) for c in train])
    Xte = np.vstack([with_history(c["X"]) for c in test])
    yte = np.concatenate([np.full(len(c["X"]), c["y"]) for c in test])
    for name, idx in GROUPS.items():
        cols = cols_with_history(idx)
        pr = fit(Xtr[:, cols], ytr, seed)
        out.setdefault(f"mlp_{name}", []).append(met(yte, pr(Xte[:, cols]) >= 0.5))
        if name == "all":
            # time-to-first-alert per attack capture (seconds = windows at W)
            off = 0
            for c in test:
                n = len(c["X"])
                if c["y"] == 1:
                    hits = np.where(pr(Xte[off:off + n, cols]) >= 0.5)[0]
                    out.setdefault("first_alert_window", []).append(float(hits[0]) if len(hits) else np.nan)
                    out.setdefault("capture_detected", []).append(float(len(hits) > 0))
                else:
                    hits = (pr(Xte[off:off + n, cols]) >= 0.5).mean()
                    out.setdefault("normal_capture_alert_frac", []).append(float(hits))
                off += n
    pin_i = FEATS.index("n_pin")
    hs_i = FEATS.index("h_src_ip")
    for nm, i in (("thr_packet_in_rate", pin_i), ("thr_src_ip_entropy", hs_i)):
        t = thr_fit(np.log1p(Xtr[:, i]), ytr)
        out.setdefault(nm, []).append(met(yte, np.log1p(Xte[:, i]) >= t))


def summarize(res):
    S = {}
    for k, v in res.items():
        if v and isinstance(v[0], dict):
            S[k] = {m: ci([r[m] for r in v]) for m in v[0]}
        else:
            S[k] = ci(v)
    return S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feat_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--W", type=float, default=1.0)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args()
    caps = load(a.feat_dir, a.W)
    labels = sorted({c["label"] for c in caps})
    assert "normal" in labels and len(labels) > 1, f"need normal and attack captures, got {labels}"
    print({l: sum(c["label"] == l for c in caps) for l in labels}, flush=True)
    R = {"inventory": {l: {"captures": sum(c["label"] == l for c in caps),
                           "windows": int(sum(len(c["X"]) for c in caps if c["label"] == l))} for l in labels}}

    # grouped CV by capture, stratified by label: round-robin captures of each label into folds
    cv = {}
    for sd in range(a.seeds):
        rng = np.random.default_rng(sd)
        fold = {}
        for l in labels:
            ids = [c["id"] for c in caps if c["label"] == l]
            rng.shuffle(ids)
            off = rng.integers(a.folds)
            for j, cid in enumerate(ids):
                fold[cid] = (j + off) % a.folds
        per_seed = {}
        for k in range(a.folds):
            test = [c for c in caps if fold[c["id"]] == k]
            train = [c for c in caps if fold[c["id"]] != k]
            if not any(c["y"] == 0 for c in train) or not any(c["y"] == 1 for c in train) or not test:
                continue
            run_split(train, test, sd, per_seed)
        for kk, v in per_seed.items():  # average folds within seed -> one value per seed
            if v and isinstance(v[0], dict):
                cv.setdefault(kk, []).append({m: float(np.nanmean([r[m] for r in v])) for m in v[0]})
            else:
                cv.setdefault(kk, []).append(float(np.nanmean(v)))
    R["grouped_cv"] = summarize(cv)
    print("grouped CV done", flush=True)

    # leakage control: permute labels across captures (capture-level), same grouped CV; expect bacc ~ 0.5
    perm = {}
    for sd in range(a.seeds):
        rng = np.random.default_rng(500 + sd)
        ys = rng.permutation([c["y"] for c in caps])
        pc = [dict(c, y=int(yv)) for c, yv in zip(caps, ys)]
        ids = [c["id"] for c in pc]
        rng.shuffle(ids)
        fold = {cid: j % a.folds for j, cid in enumerate(ids)}
        per_seed = {}
        for k in range(a.folds):
            test = [c for c in pc if fold[c["id"]] == k]
            train = [c for c in pc if fold[c["id"]] != k]
            if not any(c["y"] == 0 for c in train) or not any(c["y"] == 1 for c in train):
                continue
            if not any(c["y"] == 0 for c in test) or not any(c["y"] == 1 for c in test):
                continue
            run_split(train, test, sd, per_seed)
        if "mlp_all" in per_seed:
            perm.setdefault("mlp_all", []).append(
                {m: float(np.nanmean([r[m] for r in per_seed["mlp_all"]])) for m in per_seed["mlp_all"][0]})
    R["label_permutation_control"] = summarize(perm)
    print("permutation control done", flush=True)

    # leave-one-attack-class-out: train on normal(train captures) + other attack classes; test on held-out class
    loco = {}
    for held in [l for l in labels if l != "normal"]:
        res = {}
        for sd in range(a.seeds):
            rng = np.random.default_rng(1000 + sd)
            normals = [c for c in caps if c["label"] == "normal"]
            rng.shuffle(normals)
            cut = max(1, int(0.7 * len(normals)))
            train = [c for c in caps if c["label"] not in ("normal", held)] + normals[:cut]
            test = [c for c in caps if c["label"] == held] + normals[cut:]
            run_split(train, test, sd, res)
        loco[held] = summarize(res)
    R["leave_one_attack_class_out"] = loco
    a.out.write_text(json.dumps(R, indent=1))
    print("WROTE", a.out, flush=True)


if __name__ == "__main__":
    main()
