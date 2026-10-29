"""Leave-one-host-out on InSDN: how many independent hosts does the dataset really have, and how well is each held-out host detected?
(1) host structure: distinct Src IPs, single-flow IPs, hosts with >=500 flows, row coverage.
(2) for each host with >=500 flows: train XGBoost (GPU) on every row NOT from that host, test on that host. Report attack recall (attack hosts), false-positive rate
    (benign hosts), and per-attack-class recall. Majority vote over 3 model seeds so the number is not a single draw.
Usage (repo root): leave_one_host_out.py <out_json>"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import xgboost as xgb

sys.path.insert(0, ".")
from backend import data_full  # noqa: E402

assert torch.cuda.is_available(), "GPU required (CLAUDE.md rule 1)"
out = sys.argv[1] if len(sys.argv) > 1 else "results/leave_one_host_out.json"
df = data_full.load_insdn_raw()
lab = df["Label"].astype(str)
ID = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
X = df.drop(columns=ID).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
y = (lab.str.upper() != "BENIGN").astype(int).values
src = df["Src IP"].astype(str).values
cnt = pd.Series(src).value_counts()
R = {"rows": len(df), "distinct_src_ips": int(len(cnt)), "single_flow_src_ips": int((cnt == 1).sum()),
     "hosts_ge_500_flows": int((cnt >= 500).sum()), "rows_in_hosts_ge_500": int(cnt[cnt >= 500].sum()), "hosts": {}}
print({k: v for k, v in R.items() if k != "hosts"}, flush=True)
for h in cnt[cnt >= 500].index:
    te = np.where(src == h)[0]
    tr = np.where(src != h)[0]
    preds = []
    for seed in range(3):
        m = xgb.XGBClassifier(n_estimators=200, max_depth=6, tree_method="hist", device="cuda", random_state=seed).fit(X.iloc[tr], y[tr])
        preds.append(m.predict(X.iloc[te]))
    p = np.mean(preds, axis=0) >= 0.5
    ate = y[te] == 1
    lt = lab.iloc[te].values
    d = {"rows": int(len(te)), "attack_rows": int(ate.sum()), "labels": sorted(set(lt)),
         "recall_attack": float(p[ate].mean()) if ate.any() else None,
         "fpr_benign": float(p[~ate].mean()) if (~ate).any() else None,
         "recall_by_class": {c: float(p[lt == c].mean()) for c in sorted(set(lt)) if c.upper() != "BENIGN"},
         "train_rows": int(len(tr)), "train_attack_classes": sorted(set(lab.iloc[tr]) - {"BENIGN"})}
    R["hosts"][h] = d
    print(h, d["rows"], "recall", d["recall_attack"], "fpr", d["fpr_benign"], d["recall_by_class"], flush=True)
R["note"] = "XGBoost on numeric flow features without IPs/ports/Flow ID/timestamp; majority of 3 model seeds; train = all rows from other hosts incl. all spoofed single-flow sources"
Path(out).parent.mkdir(exist_ok=True)
json.dump(R, open(out, "w"), indent=1)
