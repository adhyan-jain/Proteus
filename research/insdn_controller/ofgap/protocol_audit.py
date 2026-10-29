"""Protocol audit: does a random flow-level split overstate IDS scores? Generalises protocol_inflation.py to several datasets.
Splits (binary benign vs attack, balanced accuracy, XGBoost on GPU, 10 seeds, mean + 95% t-CI):
A random stratified 70:30 flow split; B 70:30 split grouped by source IP (degenerate splits skipped);
C per-file time-ordered split (earliest 70% of each file train, latest 30% test); D identifier-only probe (Flow ID, IPs, ports).
E (mechanism): fraction of test rows whose full numeric feature vector exactly duplicates a train row (also reported for B, C).
Usage: protocol_audit.py --dataset {insdn,cicids2017,ukmddosdn} [--max-rows N] [--out path] (run from repo root)"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from scipy import stats
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

sys.path.insert(0, ".")
from backend import data_full  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dataset", required=True, choices=["insdn", "cicids2017", "ukmddosdn"])
ap.add_argument("--max-rows", type=int, default=0, help="stratified (by label x file) subsample cap; 0 = no cap")
ap.add_argument("--out", default=None)
args = ap.parse_args()
assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
out = args.out or f"results/protocol_audit_{args.dataset}.json"


def load_cicids():
    frames = []
    for f in data_full.CICIDS2017_FILES:
        d = pd.read_csv(data_full.CICIDS2017_DIR / f, low_memory=False)
        d.columns = [c.strip() for c in d.columns]
        d["__source_day"] = f.replace("-WorkingHours.csv", "")
        for c in d.columns:
            if c not in ("Flow ID", "Src IP", "Dst IP", "Timestamp", "Label", "__source_day"):
                d[c] = pd.to_numeric(d[c], errors="coerce").astype(np.float32)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


if args.dataset == "insdn":
    df = data_full.load_insdn_raw()
elif args.dataset == "cicids2017":
    df = load_cicids()
else:
    flows = list(Path("data/raw/ukmddosdn").glob("*.csv"))
    if not flows:
        sys.exit("SKIP ukmddosdn: data/raw/ukmddosdn holds only PCAPs (syn/udp flood), no labelled flow CSV and no benign class; "
                 "flow extraction would need CICFlowMeter on PCAPs and benign traffic is absent. Not synthesising.")
    raise SystemExit("ukmddosdn flow CSV present but no loader written")

n_full = len(df)
cap = None
if args.max_rows and len(df) > args.max_rows:
    frac = args.max_rows / len(df)
    key = (df["Label"].astype(str).str.upper() != "BENIGN").astype(str) + df["__source_day"].astype(str)
    df = df.groupby(key, group_keys=False).sample(frac=frac, random_state=0).sort_index().reset_index(drop=True)
    cap = dict(max_rows=args.max_rows, rows_before=n_full, rows_after=len(df), method="stratified by (attack?, source file), random_state=0")

y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values
ts = pd.to_datetime(df["Timestamp"], errors="coerce", dayfirst=True)
ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
idf = pd.DataFrame({c: pd.factorize(df[c].astype(str))[0] for c in ("Flow ID", "Src IP", "Dst IP")})
idf["Src Port"], idf["Dst Port"] = pd.to_numeric(df["Src Port"], errors="coerce").fillna(0), pd.to_numeric(df["Dst Port"], errors="coerce").fillna(0)
rowhash = pd.util.hash_pandas_object(X, index=False).values
print("rows", len(X), "features", X.shape[1], "attack frac %.3f" % y.mean(), flush=True)


def fit_eval(Xa, ya, tr, te, seed):
    m = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
    m.fit(Xa.iloc[tr], ya[tr])
    return float(balanced_accuracy_score(ya[te], m.predict(Xa.iloc[te])))


def dup(tr, te):
    return float(np.isin(rowhash[te], rowhash[tr]).mean())


def summ(v):
    a = np.array(v)
    return dict(n=len(a), mean=float(a.mean()), ci95=float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else None, per_seed=[float(x) for x in a])


idx = np.arange(len(X))
R = {"dataset": args.dataset, "rows": len(X), "features": int(X.shape[1]), "row_cap": cap}
A, D, EA = [], [], []
for seed in range(10):
    tr, te = train_test_split(idx, test_size=0.3, stratify=y, random_state=seed)
    A.append(fit_eval(X, y, tr, te, seed))
    D.append(fit_eval(idf, y, tr, te, seed))
    EA.append(dup(tr, te))
R["A_random_flow_split"], R["D_identifier_only_random_split"] = summ(A), summ(D)
R["E_test_rows_duplicating_train_row_splitA"] = summ(EA)
print("A %.4f  D %.4f  E(dup) %.4f" % (np.mean(A), np.mean(D), np.mean(EA)), flush=True)

B, EB, skipped = [], [], 0
for seed in range(40):
    if len(B) == 10:
        break
    tr, te = next(GroupShuffleSplit(1, test_size=0.3, random_state=seed).split(X, y, groups=df["Src IP"].values))
    if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
        skipped += 1
        continue
    B.append(fit_eval(X, y, tr, te, seed))
    EB.append(dup(tr, te))
R["B_source_ip_grouped_split"], R["B_skipped_degenerate_splits"] = (summ(B) if B else None), skipped
R["E_dup_splitB"] = summ(EB) if len(EB) > 1 else None
print("B done", flush=True)

tr_idx, te_idx = [], []
for f, g in df.groupby("__source_day"):
    order = g.index.values[np.argsort(ts.loc[g.index].values.astype("int64"), kind="stable")]
    k = int(0.7 * len(order))
    tr_idx += list(order[:k])
    te_idx += list(order[k:])
tr_idx, te_idx = np.array(tr_idx), np.array(te_idx)
ok = len({*y[te_idx]}) == 2 and len({*y[tr_idx]}) == 2
R["C_time_ordered_split"] = summ([fit_eval(X, y, tr_idx, te_idx, s) for s in range(10)]) if ok else None
R["E_dup_splitC"] = dup(tr_idx, te_idx)
R["protocol_note"] = "binary benign vs attack; C = per-file chronological 70:30 (deterministic split; CI reflects only model seed); E = fraction of test rows with an exact full-feature-vector duplicate in train"
Path(out).parent.mkdir(exist_ok=True)
json.dump(R, open(out, "w"), indent=1)
for k in ("A_random_flow_split", "B_source_ip_grouped_split", "C_time_ordered_split", "D_identifier_only_random_split", "E_test_rows_duplicating_train_row_splitA"):
    print(k, None if R[k] is None else "%.4f +- %s (n=%d)" % (R[k]["mean"], R[k]["ci95"], R[k]["n"]))
print("E_dup_splitC", R["E_dup_splitC"], "skipped IP-grouped splits:", skipped)
