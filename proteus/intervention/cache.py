"""One-time cache of the unified CICIDS2017 arrays plus per-row group ids (SPEC v1.1, section 3).

The group id of a row is a 64-bit blake2b hash of its float32 feature bytes. Every partition in
`protocol.py` is made on groups, so rows with identical feature vectors can never land on both
sides of a train/eval boundary (spec risk L4).

Why a cache: parsing the five CSVs (2.1M rows, ~1.1 GB on disk) and hashing every row takes minutes
and several GB of RAM. P0 replays 5 seeds x 2 budgets x 3 conditions, so it must load a compact .npz
instead of re-parsing for every run.

Content is unchanged from the existing pipeline: the rows, the cleaning and the feature columns are
exactly those of `data_full.load_cicids2017_raw` -> `clean_and_unify_cicids2017` ->
`get_dummies(protocol)`. The ONLY difference is memory behaviour: each day is read and cleaned on
its own (cleaning is row-wise, so the result is identical) and its identifier / string columns are
dropped immediately, instead of concatenating all five raw frames first. A test builds both ways on
a fixture and requires bit-identical arrays.

Format (`results/cache/cicids2017_v1.npz`, uncompressed, loadable with `allow_pickle=False`):
  X (n, d) float32   features: the numeric CICFlowMeter columns in raw order, then one-hot protocol
  y (n,)   int64     LabelEncoder over ALL days (taxonomy only, risk L13; sorted label strings)
  day (n,) <U..      source day ("Monday" ... "Friday")
  group (n,) uint64  blake2b-64 of the float32 row bytes, -0.0 canonicalised to 0.0
  class_names, feature_names  fixed-width string arrays
  version            CACHE_VERSION
Provenance sidecar `cicids2017_v1.provenance.json`: source file sizes + SHA-256 (checked against
`data/MANIFEST.md`), per-day row counts before/after cleaning, array SHA-256s, the group
fingerprint that `PartitionManifest.data_fingerprint` is computed from, git SHA, library versions,
build time and peak memory. `load_cache` refuses a cache without a matching sidecar.

CLI:  python -m proteus.intervention.cache status
      python -m proteus.intervention.cache build [--min-available-gib 4] [--skip-source-verify]
"""
import proteus.config  # noqa: F401 -- must import before numpy/pandas/sklearn to cap BLAS/OMP threads

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from proteus.intervention.provenance import REPO_ROOT, git_state, library_versions, utc_now_iso

log = logging.getLogger("proteus.intervention.cache")

CACHE_VERSION = 1
CACHE_PATH = REPO_ROOT / "results" / "cache" / f"cicids2017_v{CACHE_VERSION}.npz"
MANIFEST_MD = REPO_ROOT / "data" / "MANIFEST.md"
# Conservative: the day-wise build peaks at roughly the final float32 matrix twice (~1.5 GB) plus the
# largest day's raw frame (~1 GB) and interpreter overhead. This number is an estimate, not a
# measurement; the real peak is recorded in the provenance sidecar after the first build.
MIN_AVAILABLE_GIB = 4.0


class MemoryBlocker(RuntimeError):
    """Raised instead of starting the full load when available RAM is below the safe margin."""


@dataclass(frozen=True)
class DataBundle:
    X: np.ndarray            # (n, d) float32
    y: np.ndarray            # (n,) int64, LabelEncoder over ALL days (taxonomy only, risk L13)
    day: np.ndarray          # (n,) str, source day
    group: np.ndarray        # (n,) uint64, hash of the feature bytes
    class_names: list
    feature_names: list

    def __post_init__(self):
        n = len(self.X)
        for name in ("y", "day", "group"):
            if len(getattr(self, name)) != n:
                raise ValueError(f"DataBundle.{name} has length {len(getattr(self, name))}, "
                                 f"expected {n}")


def hash_rows(X, chunk=100_000):
    """64-bit hash per row of the float32 feature bytes. -0.0 is canonicalised to 0.0."""
    X = np.asarray(X, dtype=np.float32)
    out = np.empty(len(X), dtype=np.uint64)
    for s in range(0, len(X), chunk):
        block = np.ascontiguousarray(X[s:s + chunk] + np.float32(0.0))
        for i in range(len(block)):
            digest = hashlib.blake2b(block[i].tobytes(), digest_size=8).digest()
            out[s + i] = int.from_bytes(digest, "little")
    return out


def group_fingerprint(group):
    """Same formula as `PartitionManifest.data_fingerprint`."""
    return hashlib.sha256(np.ascontiguousarray(group).tobytes()).hexdigest()


# --------------------------------------------------------------------------------------- memory
def memory_report():
    """MemAvailable / MemTotal / swap from /proc/meminfo, in GiB."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) / (1024 ** 2)      # kB -> GiB
    return {"mem_total_gib": info["MemTotal"], "mem_available_gib": info["MemAvailable"],
            "mem_free_gib": info["MemFree"], "swap_total_gib": info["SwapTotal"],
            "swap_used_gib": info["SwapTotal"] - info["SwapFree"]}


def available_memory_gib():
    return memory_report()["mem_available_gib"]


def require_memory(min_gib, what):
    avail = available_memory_gib()
    if avail < min_gib:
        raise MemoryBlocker(
            f"refusing to {what}: {avail:.2f} GiB RAM available < required {min_gib:.2f} GiB "
            f"(see memory_report()). Free memory and retry; nothing was loaded.")
    return avail


# -------------------------------------------------------------------------------------- sources
def provenance_path(path=CACHE_PATH):
    path = Path(path)
    return path.with_name(path.name.replace(".npz", "") + ".provenance.json")


def manifest_sha256s(manifest_md=MANIFEST_MD):
    """{file name: sha256} for the corrected-CICIDS2017 table in data/MANIFEST.md."""
    text = Path(manifest_md).read_text()
    pat = re.compile(r"\|\s*([\w.\-]+WorkingHours\.csv)\s*\|[^|]*\|[^|]*\|\s*([0-9a-f]{64})\s*\|")
    return {m.group(1): m.group(2) for m in pat.finditer(text)}


def _sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def verify_sources(source_dir, files, manifest_md=MANIFEST_MD):
    """Hash every source CSV and compare with data/MANIFEST.md. Raises on any mismatch."""
    expected = manifest_sha256s(manifest_md)
    out = {}
    for fname in files:
        fpath = Path(source_dir) / fname
        if not fpath.exists():
            raise FileNotFoundError(f"expected CICIDS2017 file missing: {fpath}")
        got = _sha256_file(fpath)
        out[fname] = {"bytes": fpath.stat().st_size, "sha256": got,
                      "manifest_sha256": expected.get(fname),
                      "matches_manifest": expected.get(fname) == got}
        if not out[fname]["matches_manifest"]:
            raise RuntimeError(f"{fname}: sha256 {got} does not match data/MANIFEST.md "
                               f"({expected.get(fname)}); the dataset is not the verified one")
    return out


# ---------------------------------------------------------------------------------------- build
def _build_arrays(source_dir, files):
    """Day-wise equivalent of load_cicids2017_raw -> clean_and_unify_cicids2017 -> get_dummies."""
    import gc
    import pandas as pd
    from proteus.data_full import _load_one_file, clean_and_unify_cicids2017, get_feature_schema

    Xs, protos, labels, days = [], [], [], []
    per_day, feature_cols = {}, None
    for fname in files:
        raw = _load_one_file(Path(source_dir) / fname)
        day = fname.replace("-WorkingHours.csv", "")
        raw["__source_day"] = day
        n_raw = len(raw)
        df = clean_and_unify_cicids2017(raw)
        del raw
        cols = get_feature_schema(df)["feature_columns"]
        if feature_cols is None:
            feature_cols = cols
        elif cols != feature_cols:
            raise RuntimeError(f"{fname}: feature columns differ from the first day's")
        Xs.append(df[cols].to_numpy(dtype=np.float32))
        protos.append(df["protocol"].to_numpy())
        labels.append(df["label"].astype(str).to_numpy())
        days.append(df["__source_day"].astype(str).to_numpy())
        per_day[day] = {"rows_loaded": int(n_raw), "rows_kept": int(len(df))}
        del df
        gc.collect()
        log.info("cached %s: %d -> %d rows after cleaning", day, n_raw, per_day[day]["rows_kept"])

    dummies = pd.get_dummies(pd.DataFrame({"protocol": np.concatenate(protos)}),
                             columns=["protocol"])
    X_num = np.concatenate(Xs)
    del Xs
    gc.collect()
    X = np.concatenate([X_num, dummies.to_numpy(dtype=np.float32)], axis=1)
    del X_num
    feature_names = list(feature_cols) + list(dummies.columns)

    all_labels = np.concatenate(labels)
    classes = np.unique(all_labels)                     # sorted, exactly what LabelEncoder uses
    y = np.searchsorted(classes, all_labels).astype(np.int64)
    day_arr = np.concatenate(days).astype(str)
    return X, y, day_arr, [str(c) for c in classes], [str(c) for c in feature_names], per_day


def build_cache(path=CACHE_PATH, *, source_dir=None, files=None,
                min_available_gib=MIN_AVAILABLE_GIB, check_sources=True,
                manifest_md=MANIFEST_MD, force_low_memory=False):
    """Load, clean and hash the full corpus once, write the .npz and its provenance sidecar
    atomically. Refuses (MemoryBlocker) before reading anything when RAM is below the margin."""
    import resource
    from proteus.data_full import CICIDS2017_DIR, CICIDS2017_FILES
    from proteus.intervention.serialize import write_json

    source_dir = Path(source_dir) if source_dir is not None else CICIDS2017_DIR
    files = list(files) if files is not None else list(CICIDS2017_FILES)
    mem_before = memory_report()
    if not force_low_memory:
        require_memory(min_available_gib, "build the CICIDS2017 cache")
    t0 = time.perf_counter()

    sources = verify_sources(source_dir, files, manifest_md) if check_sources else None
    X, y, day, class_names, feature_names, per_day = _build_arrays(source_dir, files)
    group = hash_rows(X)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name.replace(".npz", "") + ".tmp.npz")
    np.savez(tmp, X=X, y=y, day=day, group=group,
             class_names=np.array(class_names, dtype=str),
             feature_names=np.array(feature_names, dtype=str),
             version=np.array(CACHE_VERSION))

    prov = {
        "kind": "cicids2017_unified_arrays", "cache_version": CACHE_VERSION,
        "built_utc": utc_now_iso(), **git_state(), "versions": library_versions(),
        "builder": "proteus.intervention.cache.build_cache (day-wise cleaning; content identical "
                   "to data_full.load_cicids2017_raw -> clean_and_unify_cicids2017 -> get_dummies)",
        "source": {"dir": str(source_dir), "files": sources,
                   "verified_against_manifest": bool(check_sources)},
        "cleaning_per_day": per_day,
        "n_rows": int(len(X)), "n_features": int(X.shape[1]),
        "feature_names_sha256": hashlib.sha256("\n".join(feature_names).encode()).hexdigest(),
        "class_names": class_names,
        "class_counts": {class_names[i]: int(c)
                         for i, c in enumerate(np.bincount(y, minlength=len(class_names)))},
        "rows_per_day": {str(d): int(c) for d, c in zip(*np.unique(day, return_counts=True))},
        "arrays": {"X_sha256": hashlib.sha256(np.ascontiguousarray(X).tobytes()).hexdigest(),
                   "y_sha256": hashlib.sha256(y.tobytes()).hexdigest(),
                   "day_sha256": hashlib.sha256("\n".join(day.tolist()).encode()).hexdigest()},
        "group_hash": {"algorithm": "blake2b digest_size=8 of float32 row bytes, -0.0 -> 0.0",
                       "fingerprint_sha256": group_fingerprint(group),
                       "n_unique_groups": int(len(np.unique(group)))},
        "build": {"wall_clock_s": round(time.perf_counter() - t0, 1),
                  "peak_rss_gib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                                        / (1024 ** 2), 2),
                  "memory_before": mem_before, "forced_low_memory": bool(force_low_memory)},
    }
    write_json(provenance_path(path), prov)
    os.replace(tmp, path)               # the npz appears last: a cache without a sidecar never loads
    return path


def load_provenance(path=CACHE_PATH):
    p = provenance_path(path)
    if not p.exists():
        raise FileNotFoundError(f"{p} not found: the cache has no provenance sidecar; rebuild it")
    return json.loads(p.read_text())


def load_cache(path=CACHE_PATH, deep_verify=False):
    """Load the cache and check it against its provenance sidecar (group fingerprint always;
    X hash with deep_verify=True)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m proteus.intervention.cache build` once first.")
    prov = load_provenance(path)
    z = np.load(path, allow_pickle=False)
    if int(z["version"]) != CACHE_VERSION or prov["cache_version"] != CACHE_VERSION:
        raise RuntimeError(f"cache version {int(z['version'])} != {CACHE_VERSION}; rebuild it")
    bundle = DataBundle(X=z["X"], y=z["y"], day=z["day"], group=z["group"],
                        class_names=[str(c) for c in z["class_names"]],
                        feature_names=[str(c) for c in z["feature_names"]])
    if group_fingerprint(bundle.group) != prov["group_hash"]["fingerprint_sha256"]:
        raise RuntimeError("cache group ids do not match the provenance sidecar; rebuild it")
    if len(bundle.X) != prov["n_rows"] or bundle.X.shape[1] != prov["n_features"]:
        raise RuntimeError("cache shape does not match the provenance sidecar; rebuild it")
    if deep_verify and hashlib.sha256(np.ascontiguousarray(bundle.X).tobytes()).hexdigest() != \
            prov["arrays"]["X_sha256"]:
        raise RuntimeError("cache X does not match the provenance sidecar; rebuild it")
    return bundle


def cache_status(path=CACHE_PATH):
    path = Path(path)
    mem = memory_report()
    status = {"cache_path": str(path), "cache_exists": path.exists(),
              "provenance_exists": provenance_path(path).exists(),
              "memory": mem, "min_available_gib_for_build": MIN_AVAILABLE_GIB,
              "build_memory_ok": mem["mem_available_gib"] >= MIN_AVAILABLE_GIB}
    if status["provenance_exists"]:
        prov = load_provenance(path)
        status["built_utc"] = prov["built_utc"]
        status["n_rows"] = prov["n_rows"]
    return status


def main(argv=None):
    from proteus.intervention.serialize import dumps_strict
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    b = sub.add_parser("build")
    b.add_argument("--min-available-gib", type=float, default=MIN_AVAILABLE_GIB)
    b.add_argument("--skip-source-verify", action="store_true",
                   help="do not hash the CSVs against data/MANIFEST.md (recorded in provenance)")
    b.add_argument("--force-low-memory", action="store_true",
                   help="bypass the memory guard (recorded in provenance)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.cmd == "status":
        print(dumps_strict(cache_status()))
        return 0
    try:
        out = build_cache(min_available_gib=args.min_available_gib,
                          check_sources=not args.skip_source_verify,
                          force_low_memory=args.force_low_memory)
    except MemoryBlocker as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    print(f"cache written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
