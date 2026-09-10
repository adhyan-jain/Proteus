"""Full-scale unified data pipeline (Stage 1 of the paper-grade scale-up).

Loads the corrected CICIDS2017 (WTMC-2021) dataset at full scale. Does NOT touch or replace
`proteus/data.py`, which remains the demo UI's data source.

InSDN support is scaffolded (`load_insdn`, `UNIFIED_SCHEMA` is dataset-agnostic) but not yet
implemented -- InSDN acquisition is blocked pending Kaggle API credentials. Calling
`load_insdn()` raises NotImplementedError with that explanation rather than silently no-op'ing.
"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.data_full")

DATA_DIR = Path(__file__).parent.parent / "data"
CICIDS2017_DIR = DATA_DIR / "raw" / "cicids2017"

CICIDS2017_FILES = [
    "Monday-WorkingHours.csv",
    "Tuesday-WorkingHours.csv",
    "Wednesday-WorkingHours.csv",
    "Thursday-WorkingHours.csv",
    "Friday-WorkingHours.csv",
]

# Columns that are flow/connection identifiers, not model features -- excluded from X but
# kept available for schema documentation / potential future temporal analysis.
IDENTIFIER_COLS = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Timestamp"]

# The unified schema is "whatever numeric CICFlowMeter-style flow features are common to a
# source dataset", normalized to snake_case with a stable naming convention, so that a second
# per-source loader (e.g. InSDN, once available) can map its own columns onto the same names
# without requiring changes to downstream consumers (classifier/GAN/drift/fidelity code).
def _to_unified_colname(col: str) -> str:
    return (
        col.strip()
        .lower()
        .replace("/", "_per_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def _clean_label(label: str) -> str:
    """CICIDS2017-WTMC2021 labels a fraction of rows '<Attack> - Attempted' for attacks that
    didn't fully succeed. We keep these as their own subclass rather than merging into the
    base attack class or into BENIGN, since collapsing them either way would misrepresent
    what the model is actually being asked to detect -- an explicit modeling choice, logged
    here rather than done silently."""
    return label.strip()


def _load_one_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    return df


def load_cicids2017_raw() -> pd.DataFrame:
    if not CICIDS2017_DIR.exists():
        raise FileNotFoundError(
            f"{CICIDS2017_DIR} not found. Download+extract the WTMC-2021 corrected CICIDS2017 "
            f"dataset first (see data/MANIFEST.md for source URL and checksum).")

    frames = []
    for fname in CICIDS2017_FILES:
        fpath = CICIDS2017_DIR / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Expected CICIDS2017 file missing: {fpath}")
        df = _load_one_file(fpath)
        df["__source_day"] = fname.replace("-WorkingHours.csv", "")
        frames.append(df)
        log.info(f"Loaded {fname}: {len(df):,} rows")

    full = pd.concat(frames, ignore_index=True)
    log.info(f"Concatenated CICIDS2017: {len(full):,} rows total across {len(frames)} files")
    return full


def clean_and_unify_cicids2017(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["Label"] = df["Label"].astype(str).map(_clean_label)

    n_before = len(df)

    numeric_cols = [c for c in df.columns
                     if c not in IDENTIFIER_COLS + ["Label", "Protocol", "__source_day"]]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # CICFlowMeter is known to emit +/-inf for rate features (e.g. Flow Bytes/s) on
    # near-zero-duration flows. Replace with NaN so they're caught by the same
    # missing-value accounting as genuine NaNs, rather than silently poisoning downstream
    # float32 casts.
    n_inf = int(np.isinf(df[numeric_cols].values).sum())
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)

    n_nan_rows = int(df[numeric_cols].isna().any(axis=1).sum())
    df = df.dropna(subset=numeric_cols)
    n_after = len(df)
    n_dropped = n_before - n_after

    log.info(f"Data cleaning: {n_inf:,} inf values replaced with NaN; "
             f"{n_nan_rows:,} rows had >=1 NaN/inf feature; "
             f"dropped {n_dropped:,}/{n_before:,} rows ({n_dropped/n_before:.3%}) with "
             f"missing/invalid features")

    for c in numeric_cols:
        df[c] = df[c].astype(np.float32)

    df = df.rename(columns={c: _to_unified_colname(c) for c in df.columns})
    df = df.rename(columns={"label": "label", "protocol": "protocol"})

    return df


def get_feature_schema(df: pd.DataFrame) -> dict:
    excluded = {_to_unified_colname(c) for c in IDENTIFIER_COLS} | {
        "label", "protocol", "__source_day"}
    feature_cols = [c for c in df.columns if c not in excluded]
    return {
        "feature_columns": feature_cols,
        "n_features": len(feature_cols),
        "categorical_columns": ["protocol"],
        "identifier_columns": [_to_unified_colname(c) for c in IDENTIFIER_COLS],
        "label_column": "label",
    }


def class_distribution_report(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["label"].value_counts()
    frac = counts / counts.sum()
    return pd.DataFrame({"count": counts, "fraction": frac})


def load_data_full(test_size=0.15, val_size=0.15, random_state=42):
    """Full CICIDS2017 pipeline: load -> clean/unify -> stratified train/val/test split.

    Returns a dict mirroring the shape of proteus.data.load_data()'s return value, but at
    full scale and with the real (uncollapsed) CICIDS2017 label taxonomy, plus a `val` split.
    """
    raw = load_cicids2017_raw()
    df = clean_and_unify_cicids2017(raw)
    schema = get_feature_schema(df)

    log.info("Full class distribution (post-cleaning):")
    log.info("\n" + class_distribution_report(df).to_string())

    df = pd.get_dummies(df, columns=["protocol"])
    feature_cols = [c for c in df.columns
                     if c not in ("label", "__source_day") and
                     not any(c == ic for ic in schema["identifier_columns"])]

    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    y = le.fit_transform(df["label"])
    X = df[feature_cols].astype(np.float32)

    X_train, X_temp, y_train, y_temp = train_test_split(
        X.values, y, test_size=(test_size + val_size), stratify=y, random_state=random_state)
    rel_test = test_size / (test_size + val_size)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=rel_test, stratify=y_temp, random_state=random_state)

    log.info(f"Split sizes -- train: {len(X_train):,}  val: {len(X_val):,}  "
             f"test: {len(X_test):,}")

    return {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "y_train": y_train, "y_val": y_val, "y_test": y_test,
        "feature_names": feature_cols,
        "class_names": list(le.classes_),
        "label_encoder": le,
        "data_source": "cicids2017-wtmc2021-corrected",
        "class_distribution": df["label"].value_counts().to_dict(),
        "n_rows_total": len(df),
        "schema": schema,
    }


def load_insdn():
    raise NotImplementedError(
        "InSDN loading is not implemented: acquisition is blocked pending Kaggle API "
        "credentials (no official direct-download mirror exists). The unified schema in "
        "this module (get_feature_schema / _to_unified_colname naming convention) is "
        "designed to accommodate an InSDN loader once the dataset is available -- add a "
        "load_insdn_raw() + clean_and_unify_insdn() pair mirroring the CICIDS2017 functions "
        "above, mapping InSDN's native column names onto the same unified snake_case schema.")


if __name__ == "__main__":
    result = load_data_full()
    print(f"\nDone. data_source={result['data_source']} "
          f"n_rows_total={result['n_rows_total']:,} "
          f"n_features={len(result['feature_names'])} "
          f"n_classes={len(result['class_names'])}")
