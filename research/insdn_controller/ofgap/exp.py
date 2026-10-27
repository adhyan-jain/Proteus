"""OpenFlow-view gap experiments on InSDN (GPU, 10 seeds, temporal split, mean +/- 95% CI).

E0  status quo: train on official InSDN CICFlowMeter CSV (OF-nameable features) -> deploy on OF poll snapshots
E1  view skew: train on FlowRemoved (complete) records -> test on poll snapshots, per polling interval T
E2  interval mismatch: train on snapshots at T_train -> test at T_test; vs pooled multi-T training (polling-aware)
E3  detection delay: polling-aware model on snapshots vs complete-record model waiting for FlowRemoved
E4  control-plane cost: fixed polling every k s vs confidence-gated adaptive polling (T=1 grid)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from ofsim import FINAL_COLS, SNAP_COLS  # noqa: E402

assert torch.cuda.is_available(), "CUDA required (CLAUDE.md rule 1)"
DEV = torch.device("cuda")
SI = {c: i for i, c in enumerate(SNAP_COLS)}
FI = {c: i for i, c in enumerate(FINAL_COLS)}
CSV_DIR = Path("/home/adhyan/Desktop/Proteus/data/raw/insdn_official/extracted/InSDN_DatasetCSV")
TRAIN_FRAC = 0.7
CAP = 30000  # max train rows per (class, source) per seed


# ---------------------------------------------------------------- features
def featurize(dur, pkts, byts, rp, rb, proto, first_len=None, first_flags=None):
    dur = np.maximum(dur, 1e-3)
    cols = [np.log1p(dur), np.log1p(pkts), np.log1p(byts), np.log1p(rp), np.log1p(rb),
            byts / np.maximum(pkts, 1), rb / np.maximum(rp, 1),
            np.log1p(pkts / dur), np.log1p(byts / dur), (rp > 0).astype(float),
            proto == 6, proto == 17, proto == 1]
    if first_len is not None:
        ff = first_flags.astype(np.int64)
        cols += [np.log1p(first_len)] + [((ff >> b) & 1) for b in range(6)]
    return np.column_stack(cols).astype(np.float32)


def snap_X(s, pkt_in=True):
    return featurize(s[:, SI["duration"]], s[:, SI["pkts"]], s[:, SI["bytes"]], s[:, SI["rev_pkts"]],
                     s[:, SI["rev_bytes"]], s[:, SI["proto"]],
                     s[:, SI["first_len"]] if pkt_in else None, s[:, SI["first_flags"]] if pkt_in else None)


def final_X(f, pkt_in=True):
    return featurize(f[:, FI["duration"]], f[:, FI["pkts"]], f[:, FI["bytes"]], f[:, FI["rev_pkts"]],
                     f[:, FI["rev_bytes"]], f[:, FI["proto"]],
                     f[:, FI["first_len"]] if pkt_in else None, f[:, FI["first_flags"]] if pkt_in else None)


# ---------------------------------------------------------------- data
class View:
    """All timelines for one (T, phase): snapshots + finals with labels and temporal split."""

    def __init__(self, data_dir: Path, T: float, phase: int):
        S, F = [], []
        for f in sorted(data_dir.glob(f"tl*_T{T:g}_p{phase}.npz")):
            z = np.load(f, allow_pickle=False)
            lab = z["entry_label"]
            if len(z["finals"]) == 0:
                continue
            fin, sn = z["finals"], z["snaps"]
            cut = np.quantile(fin[:, FI["t_start"]], TRAIN_FRAC)
            tl = int(f.name[2:4])
            for arr, idx, out in ((fin, FI, F), (sn, SI, S)):
                if len(arr) == 0:
                    continue
                e = arr[:, idx["entry"]].astype(np.int64)
                y = lab[e]
                keep = y != ""
                out.append(dict(a=arr[keep], y=(y[keep] != "Normal").astype(np.int64),
                                train=arr[keep][:, idx["t_start"]] < cut,
                                key=tl * 10**9 + e[keep]))
        cat = lambda L, k: np.concatenate([d[k] for d in L])  # noqa: E731
        self.f, self.fy, self.ftr, self.fkey = (cat(F, k) for k in ("a", "y", "train", "key"))
        self.s, self.sy, self.str_, self.skey = (cat(S, k) for k in ("a", "y", "train", "key"))


def load_csv_view():
    dfs = [pd.read_csv(f) for f in sorted(CSV_DIR.glob("*.csv"))]
    df = pd.concat(dfs, ignore_index=True)
    ts = pd.to_datetime(df["Timestamp"], format="%m/%d/%Y %H:%M", errors="coerce")
    X = featurize(df["Flow Duration"].values / 1e6, df["Tot Fwd Pkts"].values, df["TotLen Fwd Pkts"].values,
                  df["Tot Bwd Pkts"].values, df["TotLen Bwd Pkts"].values, df["Protocol"].values)
    y = (df["Label"].values != "Normal").astype(np.int64)
    return X, y, ts.values


# ---------------------------------------------------------------- model
class MLP(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.n = nn.Sequential(nn.Linear(d, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, 64), nn.ReLU(),
                               nn.Linear(64, 2))

    def forward(self, x):
        return self.n(x)


def balanced_idx(y, rng, cap=CAP):
    out = []
    for c in (0, 1):
        i = np.where(y == c)[0]
        if len(i):
            out.append(rng.choice(i, size=min(cap, len(i)), replace=False))
    return np.concatenate(out)


def fit(X, y, seed, epochs=15):
    torch.manual_seed(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    m = MLP(X.shape[1]).to(DEV)
    opt = torch.optim.AdamW(m.parameters(), lr=2e-3, weight_decay=1e-4)
    Xt = torch.tensor((X - mu) / sd, device=DEV)
    yt = torch.tensor(y, device=DEV)
    g = torch.Generator(device=DEV).manual_seed(seed)
    m.train()
    for _ in range(epochs):
        perm = torch.randperm(len(Xt), device=DEV, generator=g)
        for b in range(0, len(perm), 1024):
            i = perm[b:b + 1024]
            opt.zero_grad()
            nn.functional.cross_entropy(m(Xt[i]), yt[i]).backward()
            opt.step()
    m.eval()
    m.mu, m.sd = mu, sd
    return m


@torch.no_grad()
def score(m, X):
    out = []
    for b in range(0, len(X), 65536):
        xb = torch.tensor((X[b:b + 65536] - m.mu) / m.sd, device=DEV)
        out.append(torch.softmax(m(xb), 1)[:, 1].cpu().numpy())
    return np.concatenate(out) if out else np.zeros(0)


def metrics(y, p, thr=0.5):
    yhat = p >= thr
    tp, fp = int(((yhat == 1) & (y == 1)).sum()), int(((yhat == 1) & (y == 0)).sum())
    fn, tn = int(((yhat == 0) & (y == 1)).sum()), int(((yhat == 0) & (y == 0)).sum())
    rec = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-12)
    rec0 = tn / max(tn + fp, 1)
    bacc = (rec + rec0) / 2
    return dict(recall=rec, fpr=fpr, f1=f1, bacc=bacc, n=len(y))


def ci(vals):
    v = np.asarray(vals, dtype=float)
    h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else float("nan")
    return dict(mean=float(v.mean()), ci95=float(h), n=len(v), values=[float(x) for x in v])


def agg(rows):
    keys = rows[0].keys()
    return {k: ci([r[k] for r in rows]) for k in keys if k != "n"}


def first_poll(s):
    return s[:, SI["poll_idx"]] == 0


# ---------------------------------------------------------------- experiments
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--T", type=float, nargs="+", default=[1, 2, 5, 10])
    ap.add_argument("--phases", type=int, default=3)
    ap.add_argument("--seeds", type=int, default=10)
    a = ap.parse_args()
    Ts, R = a.T, {}
    views = {(T, p): View(a.data_dir, T, p) for T in Ts for p in range(a.phases)}
    seeds = list(range(a.seeds))
    print({f"T{k[0]:g}p{k[1]}": (len(v.f), len(v.s)) for k, v in views.items()}, flush=True)

    # E0: CSV-trained status quo (no PacketIn features: CSV lacks them)
    Xc, yc, tc = load_csv_view()
    cut = np.quantile(tc[~pd.isna(tc)].astype("int64"), TRAIN_FRAC)
    trc = ~pd.isna(tc) & (tc.astype("int64") < cut)
    e0 = {f"T{T:g}": {"csv_test": [], "snap_first_poll": [], "final": []} for T in Ts}
    for sd in seeds:
        rng = np.random.default_rng(sd)
        itr = np.where(trc)[0][balanced_idx(yc[trc], rng)]
        m = fit(Xc[itr], yc[itr], sd)
        te = ~trc
        for T in Ts:
            v = views[(T, sd % a.phases)]
            fp = first_poll(v.s) & ~v.str_
            e0[f"T{T:g}"]["csv_test"].append(metrics(yc[te], score(m, Xc[te])))
            e0[f"T{T:g}"]["snap_first_poll"].append(metrics(v.sy[fp], score(m, snap_X(v.s[fp], False))))
            e0[f"T{T:g}"]["final"].append(metrics(v.fy[~v.ftr], score(m, final_X(v.f[~v.ftr], False))))
    R["E0"] = {T: {k: agg(r) for k, r in d.items()} for T, d in e0.items()}
    print("E0 done", flush=True)

    # E1: complete-record training vs snapshot training, per T
    e1 = {f"T{T:g}": {"final->final": [], "final->snap": [], "snap->snap": []} for T in Ts}
    models_final = {}
    for sd in seeds:
        rng = np.random.default_rng(sd)
        for T in Ts:
            v = views[(T, sd % a.phases)]
            itr = np.where(v.ftr)[0]
            itr = itr[balanced_idx(v.fy[itr], rng)]
            mf = fit(final_X(v.f[itr]), v.fy[itr], sd)
            models_final[(sd, T)] = mf
            its = np.where(v.str_)[0]
            its = its[balanced_idx(v.sy[its], rng)]
            ms = fit(snap_X(v.s[its]), v.sy[its], sd)
            fp = first_poll(v.s) & ~v.str_
            e1[f"T{T:g}"]["final->final"].append(metrics(v.fy[~v.ftr], score(mf, final_X(v.f[~v.ftr]))))
            e1[f"T{T:g}"]["final->snap"].append(metrics(v.sy[fp], score(mf, snap_X(v.s[fp]))))
            e1[f"T{T:g}"]["snap->snap"].append(metrics(v.sy[fp], score(ms, snap_X(v.s[fp]))))
    R["E1"] = {T: {k: agg(r) for k, r in d.items()} for T, d in e1.items()}
    print("E1 done", flush=True)

    # E2: interval mismatch; pooled (polling-aware) model trained on all T and phases
    e2 = {f"{Ttr:g}->{Tte:g}": [] for Ttr in Ts for Tte in Ts}
    e2p = {f"pooled->{Tte:g}": [] for Tte in Ts}
    pooled = {}
    for sd in seeds:
        rng = np.random.default_rng(sd)
        single = {}
        Xp, yp = [], []
        for Ttr in Ts:
            v = views[(Ttr, sd % a.phases)]
            its = np.where(v.str_)[0]
            its = its[balanced_idx(v.sy[its], rng)]
            single[Ttr] = fit(snap_X(v.s[its]), v.sy[its], sd)
            for p in range(a.phases):
                w = views[(Ttr, p)]
                j = np.where(w.str_)[0]
                j = j[balanced_idx(w.sy[j], rng, cap=CAP // (len(Ts) * a.phases) + 1)]
                Xp.append(snap_X(w.s[j]))
                yp.append(w.sy[j])
        pooled[sd] = mp = fit(np.concatenate(Xp), np.concatenate(yp), sd)
        for Tte in Ts:
            w = views[(Tte, (sd + 1) % a.phases)]  # unseen-phase test view
            te = ~w.str_
            Xte, yte = snap_X(w.s[te]), w.sy[te]
            for Ttr in Ts:
                e2[f"{Ttr:g}->{Tte:g}"].append(metrics(yte, score(single[Ttr], Xte)))
            e2p[f"pooled->{Tte:g}"].append(metrics(yte, score(mp, Xte)))
    R["E2"] = {k: agg(r) for k, r in {**e2, **e2p}.items()}
    print("E2 done", flush=True)

    # E3: time-to-detection on attack entries (test split), pooled snapshot model vs FlowRemoved model
    e3 = {f"T{T:g}": {"snap_recall": [], "snap_median_delay_s": [], "removed_recall": [],
                      "removed_median_delay_s": []} for T in Ts}
    for sd in seeds:
        for T in Ts:
            v = views[(T, (sd + 1) % a.phases)]
            te = ~v.str_ & (v.sy == 1)
            s = v.s[te]
            det = score(pooled[sd], snap_X(s)) >= 0.5
            delay = s[:, SI["t_poll"]] - s[:, SI["t_start"]]
            keys = v.skey[te]
            dd = pd.DataFrame({"k": keys[det], "d": delay[det]}).groupby("k")["d"].min()
            n_att = len(np.unique(v.fkey[~v.ftr & (v.fy == 1)]))
            fte = ~v.ftr & (v.fy == 1)
            detf = score(models_final[(sd, T)], final_X(v.f[fte])) >= 0.5
            fd = (v.f[fte][:, FI["t_end"]] - v.f[fte][:, FI["t_start"]])[detf]
            e3[f"T{T:g}"]["snap_recall"].append(len(dd) / max(n_att, 1))
            e3[f"T{T:g}"]["snap_median_delay_s"].append(float(np.median(dd.values)) if len(dd) else float("nan"))
            e3[f"T{T:g}"]["removed_recall"].append(float(detf.mean()) if len(detf) else float("nan"))
            e3[f"T{T:g}"]["removed_median_delay_s"].append(float(np.median(fd)) if len(fd) else float("nan"))
    R["E3"] = {T: {k: ci(v) for k, v in d.items()} for T, d in e3.items()}
    print("E3 done", flush=True)

    # E4: polling policies on the T=1 grid (per-entry stats records = control-plane cost)
    if 1.0 in Ts:
        pol = {"fixed_1s": None, "fixed_2s": None, "fixed_5s": None, "fixed_10s": None, "adaptive": None}
        e4 = {k: {"recall": [], "fpr": [], "records_per_entry": [], "median_delay_s": []} for k in pol}
        for sd in seeds:
            v = views[(1.0, (sd + 1) % a.phases)]
            te = ~v.str_
            s, y, k = v.s[te], v.sy[te], v.skey[te]
            p = score(pooled[sd], snap_X(s))
            df = pd.DataFrame({"k": k, "i": s[:, SI["poll_idx"]].astype(int), "p": p, "y": y,
                               "d": s[:, SI["t_poll"]] - s[:, SI["t_start"]]}).sort_values(["k", "i"])
            for name in pol:
                if name.startswith("fixed"):
                    step = int(name.split("_")[1][:-1])
                    sel = df[df["i"] % step == 0]
                else:
                    # confidence-gated: poll at 1s; confident-benign (p<0.05) backs off to 8s
                    rows = []
                    for kk, g in df.groupby("k", sort=False):
                        nxt = 0
                        for i, pp in zip(g["i"].values, g["p"].values):
                            if i < nxt:
                                continue
                            rows.append((kk, i))
                            if pp >= 0.5:
                                break
                            nxt = i + (8 if pp < 0.05 else 1)
                    sel = df.set_index(["k", "i"]).loc[rows].reset_index()
                per = sel.groupby("k").agg(y=("y", "first"), hit=("p", lambda q: (q >= 0.5).any()), n=("p", "size"))
                hit_d = sel[sel["p"] >= 0.5].groupby("k")["d"].min()
                yy, hh = per["y"].values, per["hit"].values
                e4[name]["recall"].append(float(hh[yy == 1].mean()))
                e4[name]["fpr"].append(float(hh[yy == 0].mean()))
                e4[name]["records_per_entry"].append(float(per["n"].mean()))
                att = per.index[yy == 1]
                e4[name]["median_delay_s"].append(float(np.median(hit_d.reindex(att).dropna().values)))
        R["E4"] = {n: {k: ci(v) for k, v in d.items()} for n, d in e4.items()}
        print("E4 done", flush=True)

    a.out.write_text(json.dumps(R, indent=1))
    print("WROTE", a.out)


if __name__ == "__main__":
    main()
