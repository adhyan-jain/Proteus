"""Session-identity baseline: can host identity alone reproduce the controller-side detector's score?

Usage: python session_identity_baseline.py <pcap_root> <feat_dir> <out_json> [cache.pkl]

Rule R1 ("attacker-only IP memory"), learned on the training captures of each capture-grouped fold only:
  S_att = IPv4 PacketIn source addresses seen in kept attack windows of the training captures
  S_ben = ... in kept attack-free windows of the training captures
  predict attack iff the window contains a PacketIn source in S_att minus S_ben.
Rule R2 ("any attack IP"): predict attack iff the window contains a source in S_att.
Both use no traffic statistics, only which hosts appear. Folds, seeds, labels, kept-window masks and metrics are the
ones of exp_ctrl2 (strict labels, W=1 s, 5 folds, 10 seeds), so the numbers are comparable with Table `tab:cv`.
Window indices follow ctrlfeat.extract: t0 is the first OpenFlow message of the capture, windows are 1 s wide.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import dpkt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import exp_ctrl2  # noqa: E402
from ctrlfeat import _pin_frame  # noqa: E402
from exp_ctrl import ci, met  # noqa: E402
from ofparse import of_messages  # noqa: E402


def window_ip_sets(path: Path, n_windows: int, W: float = 1.0):
    sets = [set() for _ in range(n_windows)]
    t0 = None
    for ts, d, _v, t, b in of_messages(path):
        t0 = ts if t0 is None else t0
        if t != 10 or d != "to_ctrl":
            continue
        e = _pin_frame(b)
        if e is None or not isinstance(e.data, dpkt.ip.IP):
            continue
        w = int((ts - t0) // W)
        assert w < n_windows, (path, w, n_windows)
        sets[w].add(bytes(e.data.src))
    return sets


def main():
    root, feat_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cache = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    meta = json.loads((feat_dir / "meta.json").read_text())
    caps = exp_ctrl2.load(feat_dir, 1.0, "strict")
    if cache and cache.exists():
        ipsets = pickle.loads(cache.read_bytes())
    else:
        ipsets = {}
        for c in caps:
            ipsets[c["id"]] = window_ip_sets(root / meta[c["id"]]["file"], len(c["X"]))
            print("parsed", c["id"], flush=True)
        if cache:
            cache.write_bytes(pickle.dumps(ipsets))

    def pooled(cs, want):
        s = set()
        for c in cs:
            idx = np.flatnonzero(c["keep"] & (c["y"] == want))
            for i in idx:
                s |= ipsets[c["id"]][i]
        return s

    res = {"R1_attacker_only_ip_memory": [], "R2_any_attack_ip": [],
           "R1_within_attack_nonempty": [], "R2_within_attack_nonempty": []}
    n_seeds, n_folds = 10, 5
    for sd in range(n_seeds):
        fold = exp_ctrl2.folds_for(caps, sd, n_folds)
        per = {k: [] for k in res}
        for k in range(n_folds):
            te = [c for c in caps if fold[c["id"]] == k]
            tr = [c for c in caps if fold[c["id"]] != k]
            if not te or not any(c["y"].any() for c in tr):
                continue
            s_att, s_ben = pooled(tr, 1), pooled(tr, 0)
            r1_set, r2_set = s_att - s_ben, s_att
            ys, p1s, p2s, ams = [], [], [], []
            for c in te:
                idx = np.flatnonzero(c["keep"])
                sets = ipsets[c["id"]]
                ys.append(c["y"][idx])
                p1s.append(np.array([bool(sets[i] & r1_set) for i in idx]))
                p2s.append(np.array([bool(sets[i] & r2_set) for i in idx]))
                ams.append((c["session"] == 1) & c["nonempty"][idx])
            y, p1, p2, am = map(np.concatenate, (ys, p1s, p2s, ams))
            per["R1_attacker_only_ip_memory"].append(met(y, p1))
            per["R2_any_attack_ip"].append(met(y, p2))
            if am.any() and (y[am] == 0).any() and (y[am] == 1).any():
                per["R1_within_attack_nonempty"].append(met(y[am], p1[am]))
                per["R2_within_attack_nonempty"].append(met(y[am], p2[am]))
        for kk, v in per.items():
            res[kk].append({m: float(np.nanmean([r[m] for r in v])) for m in v[0]})
        print("seed", sd, {k: round(res[k][-1]["bacc"], 3) for k in res}, flush=True)
    summary = {k: {m: ci([r[m] for r in v]) for m in v[0]} for k, v in res.items()}
    summary["_note"] = ("strict labels, W=1 s, capture-grouped 5-fold, 10 seeds (exp_ctrl2 folds); rule learned on "
                        "training captures only; compare with v4_strict_W1.json A_grouped_cv.mlp_all")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    for k in res:
        print(k, {m: round(summary[k][m]["mean"], 4) for m in summary[k]})


if __name__ == "__main__":
    main()
