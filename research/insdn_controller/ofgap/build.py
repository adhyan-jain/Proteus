"""Build labelled OpenFlow-view datasets from InSDN PCAPs.

Usage: build.py <pcap_root> <out_dir> --T 1 2 5 10 --idle 10 --phases 3
Each leaf directory of PCAPs is one capture timeline. Entries are labelled by matching their
5-tuple against the official InSDN CSV Flow IDs (majority label); unmatched entries are dropped
and the match rate is recorded.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ofsim import flow_id, simulate  # noqa: E402

CSV_DIR = Path("/home/adhyan/Desktop/Proteus/data/raw/insdn_official/extracted/InSDN_DatasetCSV")


def load_labels():
    votes = collections.defaultdict(collections.Counter)
    for f in sorted(CSV_DIR.glob("*.csv")):
        df = pd.read_csv(f, usecols=["Flow ID", "Label"])
        for fid, lab in zip(df["Flow ID"].values, df["Label"].values):
            votes[fid][lab] += 1
    return {fid: c.most_common(1)[0][0] for fid, c in votes.items()}


def timelines(root: Path):
    groups = collections.defaultdict(list)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".pcap", ".pcapng", ".cap") or p.name.endswith(".pcap0"):
            groups[p.parent].append(p)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap_root", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--T", type=float, nargs="+", default=[1, 2, 5, 10])
    ap.add_argument("--idle", type=float, default=10.0)
    ap.add_argument("--phases", type=int, default=3)
    ap.add_argument("--max-polls", type=int, default=12)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    labels = load_labels()
    stats = {}
    for tl_i, (d, files) in enumerate(sorted(timelines(a.pcap_root).items())):
        tag = f"tl{tl_i:02d}"
        for T in a.T:
            for ph_i in range(a.phases):
                phase = T * ph_i / a.phases
                snaps, finals, keys = simulate(files, T=T, idle=a.idle, phase=phase, max_polls=a.max_polls)
                lab = []
                for k in keys:
                    f1, f2 = flow_id(k)
                    lab.append(labels.get(f1) or labels.get(f2) or "")
                lab = np.asarray(lab, dtype=object)
                np.savez_compressed(a.out_dir / f"{tag}_T{T:g}_p{ph_i}.npz", snaps=snaps.astype(np.float64),
                                    finals=finals.astype(np.float64), entry_label=lab.astype(str))
                matched = float((lab != "").mean()) if len(lab) else 0.0
                stats[f"{tag}_T{T:g}_p{ph_i}"] = {
                    "dir": str(d.relative_to(a.pcap_root)), "files": len(files),
                    "entries": len(keys), "snapshots": len(snaps), "match_rate": matched,
                    "labels": dict(collections.Counter(lab[lab != ""].tolist())),
                }
                print(tag, d.name, T, ph_i, len(keys), len(snaps), f"match={matched:.3f}", flush=True)
    (a.out_dir / "build_stats.json").write_text(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
