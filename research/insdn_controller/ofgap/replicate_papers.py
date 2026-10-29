"""Replicate (as faithfully as publicly described) two InSDN papers' pipelines, then change only the split / identifier pool.
Paper 1 SDNGuardStack (arXiv 2604.20934): top-15 MI features (identifiers in pool), stacking DT/ET/MLP + LightGBM meta, 80/20, 8-class.
Paper 2 Ataa et al. Sci Rep 2024: identifiers removed, numeric features, standard scaling, MLP proxy, binary, 80/20 shuffle.
Usage (repo root): ofgap/replicate_papers.py <nseeds> [out_json]"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np, pandas as pd, torch
from scipy import stats
from sklearn.ensemble import ExtraTreesClassifier, StackingClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import accuracy_score, cohen_kappa_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
import lightgbm as lgb
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from backend import data_full  # noqa: E402
assert torch.cuda.is_available(), "GPU required"
NS = int(sys.argv[1]); OUT = sys.argv[2] if len(sys.argv) > 2 else "research/insdn_controller/results/replicate_papers.json"
df = data_full.load_insdn_raw()
lab = df["Label"].astype(str)
ycls, classes = pd.factorize(lab)
yb = (lab.str.upper() != "BENIGN").astype(int).values
IDC = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label", "__source_day"]
Xn = df.drop(columns=IDC).select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)
ids = pd.DataFrame({c: pd.factorize(df[c].astype(str))[0] for c in ("Flow ID", "Src IP", "Dst IP")}).astype(np.float32)
ports = pd.DataFrame({c: pd.to_numeric(df[c], errors="coerce").fillna(0) for c in ("Src Port", "Dst Port")}).astype(np.float32)
pool_id = pd.concat([Xn, ids, ports], axis=1)   # identifiers included (paper 1 protocol)
pool_noid = Xn                                   # identifiers (Flow ID, IPs, ports, timestamp) removed
groups = df["Src IP"].values
idx = np.arange(len(df))

def split(kind, seed):
    if kind == "random":
        return train_test_split(idx, test_size=0.2, stratify=ycls, random_state=seed)
    for s in range(seed * 100, seed * 100 + 200):
        tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=s).split(idx, ycls, groups=groups))
        if len(set(ycls[tr])) >= 4: return tr, te
    raise RuntimeError("no valid grouped split")

def mi_top(pool, rows, seed, k=15):
    r = np.random.RandomState(seed).choice(rows, min(60000, len(rows)), replace=False)
    mi = mutual_info_classif(pool.iloc[r].values, ycls[r], random_state=seed)
    return list(pool.columns[np.argsort(mi)[::-1][:k]])

def stack(seed):
    base = [("dt", DecisionTreeClassifier(random_state=seed)),
            ("et", ExtraTreesClassifier(n_estimators=50, n_jobs=16, random_state=seed)),
            ("mlp", make_pipeline(StandardScaler(), MLPClassifier((32,), max_iter=10, early_stopping=True, random_state=seed)))]
    return StackingClassifier(base, final_estimator=lgb.LGBMClassifier(n_estimators=100, min_child_weight=1.0, reg_lambda=1.0, random_state=seed, verbose=-1, n_jobs=16), cv=2, n_jobs=1)

def mc(tr, te, pred_seen, seen):
    # pred in original class ids; test classes absent from train count as errors
    p = pred_seen
    return dict(acc=accuracy_score(ycls[te], p), macro_f1=f1_score(ycls[te], p, average="macro", labels=np.arange(len(classes)), zero_division=0),
                kappa=cohen_kappa_score(ycls[te], p))

def summ(v):
    a = np.array(v, float)
    return dict(n=len(a), mean=float(a.mean()), ci95=float(stats.t.ppf(.975, len(a) - 1) * a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else None, per_seed=a.tolist())

R = {"rows": len(df), "classes": list(classes), "nseeds": NS, "paper1": {}, "paper2": {}, "notes": [
 "Paper1 reported (arXiv 2604.20934): accuracy 99.98%, kappa 0.9998, 8-class, 80/20. Stratification/shuffle/grouping not stated; we use stratified random as the generous reading.",
 "Hyperparameters not fetched from the paper; sklearn defaults except: ExtraTrees 50 trees, MLP (32,) 10 iters early stopping, StackingClassifier cv=2 (all for speed under a hard time budget), LightGBM meta 100 trees with min_child_weight=1.0, reg_lambda=1.0 added: plain LightGBM defaults were numerically unstable on the near-deterministic stacked probabilities (multiclass accuracy fell to 57-92% on the random split in an aborted first run, 99.98% with these settings in a diagnostic on seed 0; chosen for stability on the paper-protocol condition a, not to create any gap; the paper reports no meta hyperparameters). DT default.",
 "MI computed with mutual_info_classif on a 60k-row random sample (speed), 8-class labels, top-15. Identifier pool = numeric + factorised Flow ID/Src IP/Dst IP + Src/Dst Port (Timestamp excluded; paper's feature list includes Flow ID, Src IP, Dst IP, Src Port, Dst Port).",
 "Identifier-dropped pool removes Flow ID, Src/Dst IP, Src/Dst Port, Timestamp.",
 "MI selection 'train_only' fits selection on the training rows only; 'all_rows' selects on all rows before the split (selection leakage).",
 "Grouped split = GroupShuffleSplit by Src IP, test 20% of hosts (row share varies); test classes absent from training count as errors for 8-class metrics; macro-F1 over all 8 classes with zero_division=0.",
 "Paper2 reported (Sci Rep 2024, PMC11589109): Transformer 99.02% / CNN-LSTM 99.01% (8-class, 48 features); binary 6-feature CNN-LSTM 99.19%. Our proxy is a torch MLP (cuda) on binary labels using all numeric features (we cannot reproduce their exact 48), NOT their Transformer/CNN-LSTM; the paper states no split ratio, we use 80/20 shuffled.",
 "No 5-fold CV / 1.0000 validation claim of paper 1 was replicated.", "Single dataset load as in repo (343,889 rows)."]}
mi_all = {"id": mi_top(pool_id, idx, 0), "noid": mi_top(pool_noid, idx, 0)}
R["top15_all_rows_with_ids"] = mi_all["id"]; R["top15_all_rows_noid"] = mi_all["noid"]
print(mi_all, flush=True)

conds = [("a_random_ids", "random", "id"), ("b_grouped_ids", "grouped", "id"), ("c_random_noids", "random", "noid"), ("d_grouped_noids", "grouped", "noid")]
for cn, sk, pk in conds:
    pool = pool_id if pk == "id" else pool_noid
    for sel in ("train_only", "all_rows"):
        rec = {"acc": [], "macro_f1": [], "kappa": [], "unseen_test_share": [], "test_frac": [], "feats": []}
        for seed in range(NS):
            t0 = time.time()
            tr, te = split(sk, seed)
            f = mi_top(pool, tr, seed) if sel == "train_only" else mi_all[pk]
            seen = np.unique(ycls[tr]); rm = {c: i for i, c in enumerate(seen)}
            m = stack(seed).fit(pool.iloc[tr][f].values, np.array([rm[c] for c in ycls[tr]]))
            p = seen[m.predict(pool.iloc[te][f].values)]
            r = mc(tr, te, p, seen)
            for k in ("acc", "macro_f1", "kappa"): rec[k].append(r[k])
            rec["unseen_test_share"].append(float((~np.isin(ycls[te], seen)).mean())); rec["test_frac"].append(len(te) / len(df)); rec["feats"].append(f)
            print(cn, sel, seed, {k: round(v, 4) for k, v in r.items()}, f"{time.time()-t0:.0f}s", flush=True)
        R["paper1"][f"{cn}|{sel}"] = {k: (summ(v) if k != "feats" else v) for k, v in rec.items()}
        json.dump(R, open(OUT, "w"), indent=1)

# Paper 2 proxy
dev = "cuda"
def mlp_run(tr, te, seed):
    torch.manual_seed(seed)
    sc = StandardScaler().fit(Xn.iloc[tr].values)
    A = lambda ix: torch.tensor(np.clip(sc.transform(Xn.iloc[ix].values), -50, 50), dtype=torch.float32, device=dev)
    Xtr, Xte = A(tr), A(te); ytr = torch.tensor(yb[tr], dtype=torch.float32, device=dev)
    net = torch.nn.Sequential(torch.nn.Linear(Xtr.shape[1], 128), torch.nn.ReLU(), torch.nn.Linear(128, 64), torch.nn.ReLU(), torch.nn.Linear(64, 1)).to(dev)
    opt = torch.optim.Adam(net.parameters(), 1e-3)
    for ep in range(15):
        perm = torch.randperm(len(Xtr), device=dev)
        for i in range(0, len(perm), 512):
            b = perm[i:i + 512]; opt.zero_grad()
            torch.nn.functional.binary_cross_entropy_with_logits(net(Xtr[b]).squeeze(1), ytr[b]).backward(); opt.step()
    with torch.no_grad(): p = (net(Xte).squeeze(1) > 0).int().cpu().numpy()
    return accuracy_score(yb[te], p), f1_score(yb[te], p, average="macro")
for sk in ("random", "grouped"):
    a, f = [], []
    for seed in range(NS):
        tr, te = split(sk, seed); x, y_ = mlp_run(tr, te, seed); a.append(x); f.append(y_)
        print("paper2", sk, seed, round(x, 4), flush=True)
    R["paper2"][f"mlp_binary|{sk}"] = {"acc": summ(a), "macro_f1": summ(f)}
json.dump(R, open(OUT, "w"), indent=1)
