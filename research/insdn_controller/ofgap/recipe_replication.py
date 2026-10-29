"""Recipe replication on InSDN: feature-set recipes seen in published papers x split protocol, same classifier (XGBoost, GPU), 10 seeds.
Feature recipes (our approximations of what the papers describe, not their code or models):
  numeric      numeric flow features only, no IPs/ports/Flow ID/timestamp (Ataa-style: 'removed IP addresses, flow IDs')
  numeric+port numeric features plus Src Port and Dst Port (OptiXGB-IDS-style)
  ids_all      numeric features plus factorised Flow ID, Src IP, Dst IP, Src Port, Dst Port
  top15_mi_ids top-15 features by mutual information chosen on ALL rows before splitting, from the ids_all pool (SDNGuardStack-style)
Splits (80:20, as most papers report): random stratified, or grouped by source IP (no host in both train and test).
Metrics: binary balanced accuracy and binary accuracy, plus 8-class accuracy (test classes unseen in train count as errors).
Usage (repo root): ofgap/recipe_replication.py <out_json>"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from scipy import stats
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

sys.path.insert(0, ".")
from backend import data_full  # noqa: E402

assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
out = sys.argv[1] if len(sys.argv) > 1 else "results/recipe_replication.json"
df = data_full.load_insdn_raw()
lab = df["Label"].astype(str)
y = (lab.str.upper() != "BENIGN").astype(int).values
ycls_all, classes = pd.factorize(lab)
ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
Xn = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
ids = pd.DataFrame({c: pd.factorize(df[c].astype(str))[0] for c in ("Flow ID", "Src IP", "Dst IP")}).astype(np.float32)
ports = pd.DataFrame({c: pd.to_numeric(df[c], errors="coerce").fillna(0) for c in ("Src Port", "Dst Port")}).astype(np.float32)
pool = pd.concat([Xn, ids, ports], axis=1)

# SDNGuardStack-style selection on the full data before any split (MI on a fixed 60k-row sample for speed)
rs = np.random.RandomState(0).choice(len(pool), 60000, replace=False)
mi = mutual_info_classif(pool.iloc[rs].values, y[rs], random_state=0)
top15 = list(pool.columns[np.argsort(mi)[::-1][:15]])
recipes = {
    "numeric": Xn,
    "numeric+port": pd.concat([Xn, ports], axis=1),
    "ids_all": pool,
    "top15_mi_ids": pool[top15],
}
print("top15 by MI:", top15, flush=True)
print("rows", len(pool), "classes", list(classes), flush=True)
groups = df["Src IP"].values


def run(X, tr, te, seed):
    kw = dict(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
    mb = xgb.XGBClassifier(**kw).fit(X.iloc[tr], y[tr])
    pb = mb.predict(X.iloc[te])
    seen = np.unique(ycls_all[tr])
    remap = {c: i for i, c in enumerate(seen)}
    mm = xgb.XGBClassifier(**kw).fit(X.iloc[tr], np.array([remap[c] for c in ycls_all[tr]]))
    pm = seen[mm.predict(X.iloc[te])]
    return (float(balanced_accuracy_score(y[te], pb)), float(accuracy_score(y[te], pb)), float(accuracy_score(ycls_all[te], pm)),
            float(np.isin(ycls_all[te], seen).mean()))


def summ(v):
    a = np.array(v)
    return dict(n=len(a), mean=float(a.mean()), ci95=float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else None, per_seed=[float(x) for x in a])


idx = np.arange(len(pool))
splits = {}
for seed in range(10):
    splits.setdefault("random", []).append(train_test_split(idx, test_size=0.2, stratify=y, random_state=seed))
gs = []
for seed in range(60):
    if len(gs) == 10:
        break
    tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=seed).split(pool, y, groups=groups))
    if len({*y[tr]}) == 2 and len({*y[te]}) == 2:
        gs.append((tr, te))
splits["grouped_src_ip"] = gs
R = {"rows": len(pool), "top15_mi_selected_on_full_data": top15, "classes": list(classes),
     "note": "approximate recipes with XGBoost (GPU) only; NOT the papers' models or code. 80:20 splits. test_rows_in_unseen_class = share of test rows whose class is absent from train (grouped splits)."}
for rn, X in recipes.items():
    for sn, sp in splits.items():
        res = np.array([run(X, tr, te, s) for s, (tr, te) in enumerate(sp)])
        R[f"{rn}|{sn}"] = dict(binary_bacc=summ(res[:, 0]), binary_acc=summ(res[:, 1]), multiclass_acc=summ(res[:, 2]), test_rows_in_unseen_class=summ(1 - res[:, 3]))
        print(f"{rn:14s} {sn:15s} bacc {res[:,0].mean():.4f} acc {res[:,1].mean():.4f} 9cls {res[:,2].mean():.4f} (n={len(sp)})", flush=True)
Path(out).parent.mkdir(exist_ok=True)
json.dump(R, open(out, "w"), indent=1)
