"""Does a random flow-level split overstate InSDN scores? Same classifier and features, different splits (binary benign vs attack).
A  random stratified 70:30 flow split (the protocol of Towhid et al., 'Early Detection of Intrusion in SDN')
B  70:30 split by source IP (no host in both train and test); splits where a class vanishes from train or test are skipped
C  per-file time-ordered split: earliest 70% of each file's flows train, latest 30% test
D  identifier-only probe: IPs, ports and Flow ID alone, random 70:30 (what the split can leak, no traffic behaviour)
Features for A-C: numeric flow features without IPs, ports, Flow ID, timestamp. XGBoost on GPU. 10 seeds. Usage: protocol_inflation.py <out_json>"""
import json
import sys

import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from scipy import stats
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

sys.path.insert(0, ".")
from backend.data_full import load_insdn_raw  # noqa: E402

assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
df = load_insdn_raw()
y = (df["Label"].astype(str).str.upper() != "BENIGN").astype(int).values
ts = pd.to_datetime(df["Timestamp"], errors="coerce", dayfirst=True)
ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
idf = pd.DataFrame({c: pd.factorize(df[c].astype(str))[0] for c in ("Flow ID", "Src IP", "Dst IP")})
idf["Src Port"], idf["Dst Port"] = pd.to_numeric(df["Src Port"], errors="coerce").fillna(0), pd.to_numeric(df["Dst Port"], errors="coerce").fillna(0)
print("rows", len(X), "features", X.shape[1], "attack frac %.3f" % y.mean(), flush=True)


def fit_eval(Xa, ya, tr, te, seed):
    m = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
    m.fit(Xa.iloc[tr], ya[tr])
    return float(balanced_accuracy_score(ya[te], m.predict(Xa.iloc[te])))


def summ(v):
    a = np.array(v)
    return dict(n=len(a), mean=float(a.mean()), ci95=float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else None, per_seed=[float(x) for x in a])


idx = np.arange(len(X))
R = {"rows": len(X), "features": int(X.shape[1])}
A, D = [], []
for seed in range(10):
    tr, te = train_test_split(idx, test_size=0.3, stratify=y, random_state=seed)
    A.append(fit_eval(X, y, tr, te, seed))
    D.append(fit_eval(idf, y, tr, te, seed))
R["A_random_flow_split"], R["D_identifier_only_random_split"] = summ(A), summ(D)
print("A %.4f  D %.4f" % (np.mean(A), np.mean(D)), flush=True)

B, skipped = [], 0
for seed in range(40):
    if len(B) == 10:
        break
    tr, te = next(GroupShuffleSplit(1, test_size=0.3, random_state=seed).split(X, y, groups=df["Src IP"].values))
    if len({*y[tr]}) < 2 or len({*y[te]}) < 2:
        skipped += 1
        continue
    B.append(fit_eval(X, y, tr, te, seed))
R["B_source_ip_grouped_split"], R["B_skipped_degenerate_splits"] = (summ(B) if B else None), skipped

tr_idx, te_idx = [], []
for f, g in df.groupby("__source_day"):
    order = g.index.values[np.argsort(ts.loc[g.index].values.astype("int64"), kind="stable")]
    k = int(0.7 * len(order))
    tr_idx += list(order[:k])
    te_idx += list(order[k:])
tr_idx, te_idx = np.array(tr_idx), np.array(te_idx)
ok = len({*y[te_idx]}) == 2
R["C_time_ordered_split"] = summ([fit_eval(X, y, tr_idx, te_idx, s) for s in range(10)]) if ok else None
R["protocol_note"] = "binary benign vs attack; benign flows exist only in Normal_data.csv, so a held-out-file split is impossible"
json.dump(R, open(sys.argv[1], "w"), indent=1)
for k in ("A_random_flow_split", "B_source_ip_grouped_split", "C_time_ordered_split", "D_identifier_only_random_split"):
    print(k, None if R[k] is None else "%.4f +- %s (n=%d)" % (R[k]["mean"], R[k]["ci95"], R[k]["n"]))
print("skipped IP-grouped splits:", skipped)
