"""One-time cache of the unified CICIDS2017 arrays plus per-row group ids (SPEC v1.0, section 3).

The group id of a row is a 64-bit blake2b hash of its float32 feature bytes. Every partition in
`protocol.py` is made on groups, so rows with identical feature vectors can never land on both
sides of a train/eval boundary (spec risk L4).

Building the cache loads the full corpus once (same memory profile as
`evaluate_full._load_day_split_data`); every later run loads the small .npz instead.
"""
import proteus.config  # noqa: F401 -- must import before numpy/pandas/sklearn to cap BLAS/OMP threads

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE_VERSION = 1
CACHE_PATH = Path(__file__).parent.parent.parent / "results" / "cache" / \
    f"cicids2017_v{CACHE_VERSION}.npz"


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


def build_cache(path=CACHE_PATH):
    """Load, clean and hash the full corpus, then write the .npz atomically."""
    import gc
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder
    from proteus.data_full import (
        load_cicids2017_raw, clean_and_unify_cicids2017, get_feature_schema)

    raw = load_cicids2017_raw()
    df = clean_and_unify_cicids2017(raw)
    del raw
    gc.collect()
    schema = get_feature_schema(df)
    df = pd.get_dummies(df, columns=["protocol"])
    feature_cols = [c for c in df.columns if c not in ("label", "__source_day") and
                    c not in schema["identifier_columns"]]
    le = LabelEncoder()
    y = le.fit_transform(df["label"]).astype(np.int64)
    day = df["__source_day"].astype(str).values
    X = df[feature_cols].astype(np.float32).values
    del df
    gc.collect()

    group = hash_rows(X)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez(tmp, X=X, y=y, day=day, group=group,
             class_names=np.array(le.classes_), feature_names=np.array(feature_cols),
             version=np.array(CACHE_VERSION))
    os.replace(tmp, path)
    return path


def load_cache(path=CACHE_PATH):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run proteus.intervention.cache.build_cache() once first.")
    z = np.load(path, allow_pickle=False)
    if int(z["version"]) != CACHE_VERSION:
        raise RuntimeError(f"cache version {int(z['version'])} != {CACHE_VERSION}; rebuild it")
    return DataBundle(X=z["X"], y=z["y"], day=z["day"], group=z["group"],
                      class_names=[str(c) for c in z["class_names"]],
                      feature_names=[str(c) for c in z["feature_names"]])
