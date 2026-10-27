"""Controller-native detection with flow-ID-grounded window labels + confound controls.

Window label y=1 iff the window contains >=1 PACKET_IN whose 5-tuple matches an attack-labelled
flow in the official InSDN CSV (y=0 otherwise, including attack-free windows inside attack captures).

  A  grouped CV by capture (10 seeds): detector vs threshold baselines + ablations;
     also "within attack captures" metrics (attack vs attack-free windows of the same session)
  B  leave-one-attack-class-out
  C  cross-deployment: Metasploitable-target captures <-> OVS-target captures
  D  session-confound probe: background-only features (attack-matched PACKET_INs removed),
     capture-level session label; how separable are sessions without attack traffic?
  E  label-permutation leakage control (window labels reassigned across captures)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import FEATS, LABCOLS  # noqa: E402
from exp_ctrl import GROUPS, cols_with_history, fit, met, summarize, thr_fit, with_history  # noqa: E402

PIN_FEATS = GROUPS["packet_in_only"]
# background probe: PACKET_IN-derived features only (no PacketOut/FlowMod/FlowRemoved/stats counts)
BG_FEATS = [i for i, f in enumerate(FEATS) if f not in ("n_pout", "n_fmod", "n_frem", "n_stats") and not f.startswith("st_")]
FAMILY = {"dos": "flood", "ddos": "flood", "probe": "probe", "brute": "brute", "exploit": "exploit",
          "web": "web", "botnet": "botnet"}
DEV = torch.device("cuda")


LC = {k: i for i, k in enumerate(LABCOLS)}


def window_labels(L: np.ndarray, attack_capture: bool, scheme: str):
    """Per-window (y, keep) from PACKET_IN category counts.
    strict: y=1 iff >=1 CSV-matched attack PACKET_IN. In attack captures a window with no CSV attack match but
      with attack-only-IP or unmatched-IP PACKET_INs is ambiguous (keep=False): it is neither scored nor trained on.
    iprule: y=1 iff >=1 CSV-matched or attack-only-IP PACKET_IN; nothing excluded (sensitivity variant)."""
    csv_att = L[:, LC["att_csv"]] > 0
    ip_att = L[:, LC["att_ip"]] > 0
    unm = L[:, LC["unm_ip"]] > 0
    if scheme == "iprule":
        return (csv_att | ip_att).astype(np.int64), np.ones(len(L), bool)
    keep = np.ones(len(L), bool)
    if attack_capture:
        keep = csv_att | ~(ip_att | unm)
    return csv_att.astype(np.int64), keep


def load(d: Path, W: float, scheme: str = "strict"):
    meta = json.loads((d / "meta.json").read_text())
    caps = []
    for cid, m in sorted(meta.items()):
        X = np.load(d / f"{cid}_W{W:g}.npy")
        if len(X) == 0:
            continue
        L = np.load(d / f"{cid}_W{W:g}_lab.npy")
        Xb = np.load(d / f"{cid}_W{W:g}_bg.npy")
        assert len(L) == len(X), (cid, len(X), len(L))
        if len(Xb) < len(X):  # background view may end earlier (trailing attack-only windows)
            Xb = np.vstack([Xb, np.zeros((len(X) - len(Xb), Xb.shape[1]), Xb.dtype)])
        dep = "normal" if m["label"] == "normal" else ("metasploitable" if "metsplotable" in m["file"].lower() else "ovs")
        y, keep = window_labels(L, m["label"] != "normal", scheme)
        caps.append(dict(id=cid, label=m["label"], dep=dep, X=X, Xb=Xb[:len(X)], session=int(m["label"] != "normal"),
                         y=y, keep=keep, nonempty=X[:, 0] > 0))
    return caps


def stack(caps, key="X", extra=False):
    """History is built on every window of a capture, then ambiguous windows (keep=False) are dropped."""
    k = np.concatenate([c["keep"] for c in caps])
    X = np.vstack([with_history(c[key]) for c in caps])[k]
    y = np.concatenate([c["y"] for c in caps])[k]
    inatt = np.concatenate([np.full(len(c["X"]), c["session"]) for c in caps])[k]
    if extra:
        cap_idx = np.concatenate([np.full(len(c["X"]), i) for i, c in enumerate(caps)])[k]
        nonempty = np.concatenate([c["nonempty"] for c in caps])[k]
        return X, y, inatt, cap_idx, nonempty
    return X, y, inatt


def fit_linear(X, y, seed, epochs=60):
    """Logistic regression on the GPU with the same normalisation/weighting as exp_ctrl.fit."""
    torch.manual_seed(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    m = nn.Linear(X.shape[1], 2).to(DEV)
    w = torch.tensor([len(y) / (2 * max((y == c).sum(), 1)) for c in (0, 1)], dtype=torch.float32, device=DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-2, weight_decay=1e-3)
    Xt, yt = torch.tensor((X - mu) / sd, device=DEV), torch.tensor(y, device=DEV)
    for _ in range(epochs):
        perm = torch.randperm(len(Xt), device=DEV)
        for b in range(0, len(perm), 1024):
            i = perm[b:b + 1024]
            opt.zero_grad()
            nn.functional.cross_entropy(m(Xt[i]), yt[i], weight=w).backward()
            opt.step()
    m.eval()

    @torch.no_grad()
    def predict(Xq):
        return torch.softmax(m(torch.tensor((Xq - mu) / sd, device=DEV)), 1)[:, 1].cpu().numpy()
    return predict


def fit_xgb(X, y, seed):
    """Gradient-boosted trees on the GPU (xgboost device=cuda), class-balanced via scale_pos_weight."""
    import xgboost as xgb
    spw = float((y == 0).sum() / max((y == 1).sum(), 1))
    m = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, subsample=0.8, tree_method="hist",
                          device="cuda", scale_pos_weight=spw, random_state=seed, verbosity=0)
    m.fit(X, y)
    return lambda Xq: m.predict_proba(Xq)[:, 1]


def macro_capture_bacc(y, p, cap):
    """Mean over captures of balanced accuracy (captures lacking one class are skipped)."""
    vals = []
    for c in np.unique(cap):
        m = cap == c
        if (y[m] == 1).any() and (y[m] == 0).any():
            vals.append((p[m][y[m] == 1].mean() + (~p[m][y[m] == 0]).mean()) / 2)
    return float(np.mean(vals)) if vals else float("nan")


def _count(counts, name, caps_ids, cap_idx, y, p):
    if counts is None:
        return
    for j, cid in enumerate(caps_ids):
        m = cap_idx == j
        if m.any():
            c = counts.setdefault(name, {}).setdefault(cid, np.zeros(4))
            c += [(p[m] & (y[m] == 1)).sum(), (~p[m] & (y[m] == 1)).sum(), (~p[m] & (y[m] == 0)).sum(), (p[m] & (y[m] == 0)).sum()]


def evaluate(train, test, seed, out, counts=None):
    Xtr, ytr, _ = stack(train)
    Xte, yte, inatt, cap_idx, nonempty = stack(test, extra=True)
    ids = [c["id"] for c in test]
    nf = len(FEATS)
    for name, idx in GROUPS.items():
        cols = cols_with_history(idx)
        pr = fit(Xtr[:, cols], ytr, seed)
        p = pr(Xte[:, cols]) >= 0.5
        out.setdefault(f"mlp_{name}", []).append(met(yte, p))
        if name == "all":
            _count(counts, "mlp_all", ids, cap_idx, yte, p)
            m_att = (inatt == 1) & nonempty
            if m_att.any() and (yte[m_att] == 0).any() and (yte[m_att] == 1).any():
                out.setdefault("mlp_all_within_attack_nonempty", []).append(met(yte[m_att], p[m_att]))
                out.setdefault("mlp_all_within_attack_nonempty_macro_capture", []).append(
                    {"bacc": macro_capture_bacc(yte[m_att], p[m_att], cap_idx[m_att])})
                triv = Xte[m_att, 0] > 0   # trivial baseline "any PACKET_IN" is all-True on non-empty windows
                out.setdefault("trivial_any_packet_in_within_attack_nonempty", []).append(met(yte[m_att], triv))
            if (inatt == 0).any():
                out.setdefault("mlp_all_normal_captures_fpr", []).append(float(p[inatt == 0].mean()))
    # history-matched and single-window baselines on all features
    cols_all = cols_with_history(GROUPS["all"])
    p_lin = fit_linear(Xtr[:, cols_all], ytr, seed)(Xte[:, cols_all]) >= 0.5
    out.setdefault("linear_all_history", []).append(met(yte, p_lin))
    _count(counts, "linear_all_history", ids, cap_idx, yte, p_lin)
    p_xgb = fit_xgb(Xtr[:, cols_all], ytr, seed)(Xte[:, cols_all]) >= 0.5
    out.setdefault("xgb_all_history", []).append(met(yte, p_xgb))
    _count(counts, "xgb_all_history", ids, cap_idx, yte, p_xgb)
    cols_one = list(range(nf))   # current window only
    p_one = fit(Xtr[:, cols_one], ytr, seed)(Xte[:, cols_one]) >= 0.5
    out.setdefault("mlp_all_single_window", []).append(met(yte, p_one))
    _count(counts, "mlp_all_single_window", ids, cap_idx, yte, p_one)
    # single-feature thresholds fitted on training folds
    for nm, f in (("thr_packet_in_rate", "n_pin"), ("thr_src_ip_entropy", "h_src_ip"), ("thr_dport_entropy", "h_dport")):
        i = FEATS.index(f)
        t = thr_fit(np.log1p(Xtr[:, i]), ytr)
        pth = np.log1p(Xte[:, i]) >= t
        out.setdefault(nm, []).append(met(yte, pth))
        _count(counts, nm, ids, cap_idx, yte, pth)
    # causal per-capture-normalised PACKET_IN rate: current minus mean of the previous three windows
    i = FEATS.index("n_pin")
    def burst(X):
        return np.log1p(X[:, i]) - np.mean([np.log1p(X[:, k * nf + i]) for k in (1, 2, 3)], axis=0)
    t = thr_fit(burst(Xtr), ytr)
    pb = burst(Xte) >= t
    out.setdefault("thr_packet_in_burst", []).append(met(yte, pb))
    _count(counts, "thr_packet_in_burst", ids, cap_idx, yte, pb)


def cluster_bootstrap(caps, counts, n_boot=2000, seed=0):
    """95% percentile CI of pooled BAcc, resampling captures with replacement within class strata."""
    rng = np.random.default_rng(seed)
    classes = sorted({c["label"] for c in caps})
    by_class = {l: [c["id"] for c in caps if c["label"] == l] for l in classes}
    out = {}
    for name, per in counts.items():
        vals = []
        for _ in range(n_boot):
            tot = np.zeros(4)
            for l in classes:
                ids = [i for i in by_class[l] if i in per]
                if not ids:
                    continue
                for cid in rng.choice(ids, size=len(ids), replace=True):
                    tot += per[cid]
            tp, fn, tn, fp = tot
            if tp + fn > 0 and tn + fp > 0:
                vals.append((tp / (tp + fn) + tn / (tn + fp)) / 2)
        pt = np.zeros(4)
        for v in per.values():
            pt += v
        tp, fn, tn, fp = pt
        out[name] = {"bacc_pooled": float((tp / max(tp + fn, 1) + tn / max(tn + fp, 1)) / 2),
                     "ci95_lo": float(np.percentile(vals, 2.5)), "ci95_hi": float(np.percentile(vals, 97.5)),
                     "n_captures": len(per), "n_boot": len(vals)}
    return out


def folds_for(caps, seed, k):
    rng = np.random.default_rng(seed)
    fold = {}
    for l in sorted({c["label"] for c in caps}):
        ids = [c["id"] for c in caps if c["label"] == l]
        rng.shuffle(ids)
        off = rng.integers(k)
        for j, cid in enumerate(ids):
            fold[cid] = (j + off) % k
    return fold


def seed_mean(per_seed, acc):
    for kk, v in per_seed.items():
        if v and isinstance(v[0], dict):
            acc.setdefault(kk, []).append({m: float(np.nanmean([r[m] for r in v])) for m in v[0]})
        elif v:
            acc.setdefault(kk, []).append(float(np.nanmean(v)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feat_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--W", type=float, default=1.0)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--labels", choices=("strict", "iprule"), default="strict")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    caps = load(a.feat_dir, a.W, a.labels)
    labels = sorted({c["label"] for c in caps})
    assert "normal" in labels and len(labels) > 1, labels
    R = {"inventory": {l: {"captures": sum(c["label"] == l for c in caps),
                           "windows": int(sum(len(c["X"]) for c in caps if c["label"] == l)),
                           "windows_kept": int(sum(c["keep"].sum() for c in caps if c["label"] == l)),
                           "attack_windows": int(sum((c["y"] & c["keep"]).sum() for c in caps if c["label"] == l)),
                           "empty_attack_free_kept": int(sum(((c["y"] == 0) & c["keep"] & ~c["nonempty"]).sum()
                                                             for c in caps if c["label"] == l))} for l in labels}
         | {"label_scheme": a.labels}}
    print(R["inventory"], flush=True)

    # A grouped CV
    cv, counts = {}, {}
    for sd in range(a.seeds):
        fold = folds_for(caps, sd, a.folds)
        per = {}
        for k in range(a.folds):
            te = [c for c in caps if fold[c["id"]] == k]
            tr = [c for c in caps if fold[c["id"]] != k]
            if te and any(c["y"].any() for c in tr):
                evaluate(tr, te, sd, per, counts)
        seed_mean(per, cv)
    R["A_grouped_cv"] = summarize(cv)
    R["A_capture_cluster_bootstrap"] = cluster_bootstrap(caps, counts, a.boot)
    print("A done", flush=True)

    # B leave-one-attack-class-out
    R["B_leave_one_attack_family_out"] = {}
    normals = [c for c in caps if c["label"] == "normal"]
    for held in sorted({FAMILY[l] for l in labels if l != "normal"}):
        res = {}
        for sd in range(a.seeds):
            rng = np.random.default_rng(1000 + sd)
            nn_ = list(normals)
            rng.shuffle(nn_)
            cut = max(1, int(0.7 * len(nn_)))
            tr = [c for c in caps if c["label"] != "normal" and FAMILY[c["label"]] != held] + nn_[:cut]
            te = [c for c in caps if c["label"] != "normal" and FAMILY[c["label"]] == held] + nn_[cut:]
            evaluate(tr, te, sd, res)
        R["B_leave_one_attack_family_out"][held] = summarize(res)
    print("B done", flush=True)

    # C cross-deployment
    R["C_cross_deployment"] = {}
    for src, dst in (("metasploitable", "ovs"), ("ovs", "metasploitable")):
        res = {}
        for sd in range(a.seeds):
            rng = np.random.default_rng(2000 + sd)
            nn_ = list(normals)
            rng.shuffle(nn_)
            cut = max(1, int(0.6 * len(nn_)))
            tr = [c for c in caps if c["dep"] == src] + nn_[:cut]
            te = [c for c in caps if c["dep"] == dst] + nn_[cut:]
            evaluate(tr, te, sd, res)
        R["C_cross_deployment"][f"{src}->{dst}"] = summarize(res)
    print("C done", flush=True)

    # D session-confound probe (PACKET_IN-derived features only; windows need >=5 background PACKET_INs).
    #  D1: background = PACKET_INs not matching attack flows, all windows of every capture
    #  D2: stricter - only attack-free (y=0, kept) windows of attack captures vs windows of normal captures
    probe = {}
    cols = cols_with_history(BG_FEATS)
    for variant in ("D1_all_windows", "D2_attack_free_windows_only"):
        for sd in range(a.seeds):
            fold = folds_for(caps, sd, a.folds)
            per, base = [], []
            for k in range(a.folds):
                te = [c for c in caps if fold[c["id"]] == k]
                tr = [c for c in caps if fold[c["id"]] != k]

                def prep(cs):
                    Xs, ys = [], []
                    for c in cs:
                        H = with_history(c["Xb"])
                        ok = c["Xb"][:, 0] >= 5
                        if variant.startswith("D2") and c["session"] == 1:
                            ok &= (c["y"] == 0) & c["keep"]
                        Xs.append(H[ok][:, cols])
                        ys.append(np.full(int(ok.sum()), c["session"]))
                    return np.vstack(Xs), np.concatenate(ys)

                Xtr, ytr = prep(tr)
                Xte, yte = prep(te)
                if len(set(ytr)) < 2 or len(set(yte)) < 2:
                    continue
                per.append(met(yte, fit(Xtr, ytr, sd)(Xte) >= 0.5))
                base.append(met(yte, np.full(len(yte), bool(np.bincount(ytr).argmax()))))
            if per:
                probe.setdefault(variant, []).append({m: float(np.nanmean([r[m] for r in per])) for m in per[0]})
                probe.setdefault(variant + "_majority_baseline", []).append(
                    {m: float(np.nanmean([r[m] for r in base])) for m in base[0]})
    R["D_session_confound_probe"] = summarize(probe)
    print("D done", flush=True)

    # E permutation control: each capture receives another capture's window-label sequence
    perm = {}
    for sd in range(a.seeds):
        rng = np.random.default_rng(500 + sd)
        swap = rng.permutation(len(caps))
        pc = [dict(c, y=np.resize(caps[j]["y"], len(c["X"]))) for c, j in zip(caps, swap)]
        fold = folds_for(pc, sd, a.folds)
        per = {}
        for k in range(a.folds):
            te = [c for c in pc if fold[c["id"]] == k]
            tr = [c for c in pc if fold[c["id"]] != k]
            if te and any(c["y"].any() for c in tr) and any(c["y"].any() for c in te):
                evaluate(tr, te, sd, per)
        seed_mean({"mlp_all": per.get("mlp_all", [])}, perm)
    R["E_label_permutation_control"] = summarize(perm)
    a.out.write_text(json.dumps(R, indent=1))
    print("WROTE", a.out, flush=True)


if __name__ == "__main__":
    main()
