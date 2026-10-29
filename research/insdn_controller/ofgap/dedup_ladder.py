"""Dedup ladder on InSDN (answers 'is the random-split score just exact duplicates?' and 'is the grouped drop just a missing class?'):
binary BAcc, XGBoost GPU, 10 seeds, 70:30. Rungs: random split on all rows; random split after dropping exact numeric-feature duplicates (keep first);
grouped splits (by Src IP, and by Src IP|Dst IP|Dst Port triple) where every attack label in test also appears in train (class-coverage-controlled).
Usage (repo root): dedup_ladder.py <out_json>"""
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

assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
out = sys.argv[1] if len(sys.argv) > 1 else "results/dedup_ladder.json"
df = data_full.load_insdn_raw()
lab = df["Label"].astype(str)
ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
y = (lab.str.upper() != "BENIGN").astype(int).values
keep = ~pd.util.hash_pandas_object(X, index=False).duplicated().values
trip = (df["Src IP"].astype(str) + "|" + df["Dst IP"].astype(str) + "|" + df["Dst Port"].astype(str)).values
print("rows", len(X), "after dedup", int(keep.sum()), flush=True)


def fit(Xa, ya, tr, te, seed):
    m = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed).fit(Xa.iloc[tr], ya[tr])
    return float(balanced_accuracy_score(ya[te], m.predict(Xa.iloc[te])))


def summ(v):
    a = np.array(v)
    return dict(n=len(a), mean=float(a.mean()), ci95=float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else None, per_seed=[float(x) for x in a])


R = {"rows": len(X), "rows_after_dedup": int(keep.sum()), "attack_rows_after_dedup": int(y[keep].sum()), "benign_rows_after_dedup": int((1 - y[keep]).sum())}
for name, mask in (("all_rows", np.ones(len(X), bool)), ("dedup", keep)):
    Xs, ys, ls = X[mask].reset_index(drop=True), y[mask], lab[mask].reset_index(drop=True)
    idx = np.arange(len(Xs))
    r = [fit(Xs, ys, *train_test_split(idx, test_size=0.3, stratify=ys, random_state=s), s) for s in range(10)]
    R[f"random|{name}"] = summ(r)
    print(name, "random", np.mean(r), flush=True)
    for gname, g in (("src_ip", df["Src IP"].values[mask]), ("src_dst_dport_triple", trip[mask])):
        res, absent, degenerate = [], 0, 0
        for seed in range(200):
            if len(res) == 10:
                break
            tr, te = next(GroupShuffleSplit(1, test_size=0.3, random_state=seed).split(Xs, ys, groups=g))
            if len({*ys[tr]}) < 2 or len({*ys[te]}) < 2:
                degenerate += 1
                continue
            if not set(ls.iloc[te][ys[te] == 1]).issubset(set(ls.iloc[tr][ys[tr] == 1])):
                absent += 1
                continue
            res.append(fit(Xs, ys, tr, te, seed))
        R[f"grouped_{gname}_class_covered|{name}"] = dict(result=summ(res) if len(res) > 1 else None, splits_skipped_attack_class_absent_in_train=absent, splits_skipped_degenerate=degenerate)
        print(name, gname, "class-covered grouped", np.mean(res) if res else None, "n", len(res), "skipped(absent class)", absent, flush=True)
R["note"] = "class-covered = grouped splits kept only when every attack label in test also appears in train; dedup = exact numeric-feature-vector duplicates removed before splitting (keep first)"
Path(out).parent.mkdir(exist_ok=True)
json.dump(R, open(out, "w"), indent=1)
