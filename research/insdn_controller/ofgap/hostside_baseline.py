"""Host-side baseline: InSDN's own CICFlowMeter flow-CSV features, benign vs attack, XGBoost on GPU, 10 seeds of
stratified 70/30 row-level splits (the protocol flow-CSV papers use; rows from one session land on both sides).
Output: mean and 95% t-interval of balanced accuracy. Usage: hostside_baseline.py <out_json>"""
import json
import sys

import numpy as np
import torch
import xgboost as xgb
from scipy import stats
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, ".")
from proteus.data_full import clean_and_unify_cicids2017, load_insdn_raw  # noqa: E402

assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
df = clean_and_unify_cicids2017(load_insdn_raw())
y = (df["label"].astype(str).str.upper() != "BENIGN").astype(int).values
drop = {"label", "__source_day", "protocol"}
X = df[[c for c in df.columns if c not in drop and df[c].dtype.kind in "fiub"]].astype(np.float32)
print("rows", len(X), "features", X.shape[1], "attack frac %.3f" % y.mean(), flush=True)
accs = []
for seed in range(10):
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
    m = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed)
    m.fit(Xtr, ytr)
    accs.append(float(balanced_accuracy_score(yte, m.predict(Xte))))
a = np.array(accs)
ci = float(stats.t.ppf(0.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a)))
res = dict(rows=len(X), features=int(X.shape[1]), seeds=10, bacc_per_seed=accs, bacc_mean=float(a.mean()), bacc_ci95=ci,
           protocol="stratified 70/30 row split, XGBoost GPU, 200 trees depth 6")
json.dump(res, open(sys.argv[1], "w"), indent=1)
print("BAcc %.4f +- %.4f" % (a.mean(), ci))
