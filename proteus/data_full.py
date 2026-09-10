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
INSDN_DIR = DATA_DIR / "raw" / "insdn" / "InSDN_DatasetCSV"

CICIDS2017_FILES = [
    "Monday-WorkingHours.csv",
    "Tuesday-WorkingHours.csv",
    "Wednesday-WorkingHours.csv",
    "Thursday-WorkingHours.csv",
    "Friday-WorkingHours.csv",
]

INSDN_FILES = ["Normal_data.csv", "OVS.csv", "metasploitable-2.csv"]

# InSDN's CSVs use CICFlowMeter's abbreviated column-name convention (e.g. "Tot Fwd Pkts"),
# while the corrected CICIDS2017 files use the unabbreviated convention (e.g.
# "Total Fwd Packet"). Both are the same 84 CICFlowMeter features in the same emission order
# (verified positionally: `paste` of the two raw header rows lines up 1:1 across all 84
# columns, including the one real naming quirk -- InSDN's "CWE Flag Count" is CICIDS2017's
# "CWR Flag Count", same feature/position, not two different flags). This map is therefore
# built from that verified positional pairing, not a fuzzy/heuristic abbreviation expansion.
INSDN_TO_CICIDS2017_COLS = {
    "Flow ID": "Flow ID", "Src IP": "Src IP", "Src Port": "Src Port", "Dst IP": "Dst IP",
    "Dst Port": "Dst Port", "Protocol": "Protocol", "Timestamp": "Timestamp",
    "Flow Duration": "Flow Duration", "Tot Fwd Pkts": "Total Fwd Packet",
    "Tot Bwd Pkts": "Total Bwd packets", "TotLen Fwd Pkts": "Total Length of Fwd Packet",
    "TotLen Bwd Pkts": "Total Length of Bwd Packet", "Fwd Pkt Len Max": "Fwd Packet Length Max",
    "Fwd Pkt Len Min": "Fwd Packet Length Min", "Fwd Pkt Len Mean": "Fwd Packet Length Mean",
    "Fwd Pkt Len Std": "Fwd Packet Length Std", "Bwd Pkt Len Max": "Bwd Packet Length Max",
    "Bwd Pkt Len Min": "Bwd Packet Length Min", "Bwd Pkt Len Mean": "Bwd Packet Length Mean",
    "Bwd Pkt Len Std": "Bwd Packet Length Std", "Flow Byts/s": "Flow Bytes/s",
    "Flow Pkts/s": "Flow Packets/s", "Flow IAT Mean": "Flow IAT Mean",
    "Flow IAT Std": "Flow IAT Std", "Flow IAT Max": "Flow IAT Max",
    "Flow IAT Min": "Flow IAT Min", "Fwd IAT Tot": "Fwd IAT Total",
    "Fwd IAT Mean": "Fwd IAT Mean", "Fwd IAT Std": "Fwd IAT Std", "Fwd IAT Max": "Fwd IAT Max",
    "Fwd IAT Min": "Fwd IAT Min", "Bwd IAT Tot": "Bwd IAT Total",
    "Bwd IAT Mean": "Bwd IAT Mean", "Bwd IAT Std": "Bwd IAT Std", "Bwd IAT Max": "Bwd IAT Max",
    "Bwd IAT Min": "Bwd IAT Min", "Fwd PSH Flags": "Fwd PSH Flags",
    "Bwd PSH Flags": "Bwd PSH Flags", "Fwd URG Flags": "Fwd URG Flags",
    "Bwd URG Flags": "Bwd URG Flags", "Fwd Header Len": "Fwd Header Length",
    "Bwd Header Len": "Bwd Header Length", "Fwd Pkts/s": "Fwd Packets/s",
    "Bwd Pkts/s": "Bwd Packets/s", "Pkt Len Min": "Packet Length Min",
    "Pkt Len Max": "Packet Length Max", "Pkt Len Mean": "Packet Length Mean",
    "Pkt Len Std": "Packet Length Std", "Pkt Len Var": "Packet Length Variance",
    "FIN Flag Cnt": "FIN Flag Count", "SYN Flag Cnt": "SYN Flag Count",
    "RST Flag Cnt": "RST Flag Count", "PSH Flag Cnt": "PSH Flag Count",
    "ACK Flag Cnt": "ACK Flag Count", "URG Flag Cnt": "URG Flag Count",
    "CWE Flag Count": "CWR Flag Count", "ECE Flag Cnt": "ECE Flag Count",
    "Down/Up Ratio": "Down/Up Ratio", "Pkt Size Avg": "Average Packet Size",
    "Fwd Seg Size Avg": "Fwd Segment Size Avg", "Bwd Seg Size Avg": "Bwd Segment Size Avg",
    "Fwd Byts/b Avg": "Fwd Bytes/Bulk Avg", "Fwd Pkts/b Avg": "Fwd Packet/Bulk Avg",
    "Fwd Blk Rate Avg": "Fwd Bulk Rate Avg", "Bwd Byts/b Avg": "Bwd Bytes/Bulk Avg",
    "Bwd Pkts/b Avg": "Bwd Packet/Bulk Avg", "Bwd Blk Rate Avg": "Bwd Bulk Rate Avg",
    "Subflow Fwd Pkts": "Subflow Fwd Packets", "Subflow Fwd Byts": "Subflow Fwd Bytes",
    "Subflow Bwd Pkts": "Subflow Bwd Packets", "Subflow Bwd Byts": "Subflow Bwd Bytes",
    "Init Fwd Win Byts": "FWD Init Win Bytes", "Init Bwd Win Byts": "Bwd Init Win Bytes",
    "Fwd Act Data Pkts": "Fwd Act Data Pkts", "Fwd Seg Size Min": "Fwd Seg Size Min",
    "Active Mean": "Active Mean", "Active Std": "Active Std", "Active Max": "Active Max",
    "Active Min": "Active Min", "Idle Mean": "Idle Mean", "Idle Std": "Idle Std",
    "Idle Max": "Idle Max", "Idle Min": "Idle Min", "Label": "Label",
}

# InSDN's own label taxonomy -> a name consistent with how CICIDS2017 labels the same
# attack family, so the unified `label` column is comparable across sources. "Normal" is
# InSDN's benign class; CICIDS2017 uses "BENIGN". Multi-word InSDN labels already match
# CICIDS2017's naming for the same attack category (DDoS, DoS, Probe); BFA (Brute-Force
# Attack) and Web-Attack/BOTNET/U2R are InSDN-specific categories with no CICIDS2017
# equivalent label, kept as-is rather than force-mapped onto an unrelated CICIDS2017 label.
INSDN_LABEL_MAP = {"Normal": "BENIGN"}

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


def load_insdn_raw() -> pd.DataFrame:
    if not INSDN_DIR.exists():
        raise FileNotFoundError(
            f"{INSDN_DIR} not found. Download the InSDN dataset first (see "
            f"data/MANIFEST.md for source and file hashes).")

    frames = []
    for fname in INSDN_FILES:
        fpath = INSDN_DIR / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Expected InSDN file missing: {fpath}")
        df = pd.read_csv(fpath, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        # Rename onto CICIDS2017's column-name convention using the verified positional
        # mapping, so clean_and_unify_cicids2017's cleaning logic (inf/NaN handling, dtype
        # casting, snake_case normalization) can be reused unchanged on InSDN rows.
        df = df.rename(columns=INSDN_TO_CICIDS2017_COLS)
        df["__source_day"] = f"insdn-{fname.replace('.csv', '')}"
        frames.append(df)
        log.info(f"Loaded InSDN/{fname}: {len(df):,} rows")

    full = pd.concat(frames, ignore_index=True)
    full["Label"] = full["Label"].astype(str).str.strip().replace(INSDN_LABEL_MAP)
    log.info(f"Concatenated InSDN: {len(full):,} rows total across {len(frames)} files")
    return full


def load_insdn(test_size=0.15, val_size=0.15, random_state=42):
    """InSDN pipeline: load -> clean/unify (reusing the CICIDS2017 cleaning logic, since
    columns are renamed onto the same convention first) -> stratified train/val/test split.

    Returns a dict in the same shape as load_data_full()'s return value.
    """
    raw = load_insdn_raw()
    df = clean_and_unify_cicids2017(raw)  # reused as-is; InSDN cols already renamed to match
    schema = get_feature_schema(df)

    log.info("InSDN class distribution (post-cleaning):")
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

    log.info(f"InSDN split sizes -- train: {len(X_train):,}  val: {len(X_val):,}  "
             f"test: {len(X_test):,}")

    return {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "y_train": y_train, "y_val": y_val, "y_test": y_test,
        "feature_names": feature_cols,
        "class_names": list(le.classes_),
        "label_encoder": le,
        "data_source": "insdn",
        "class_distribution": df["label"].value_counts().to_dict(),
        "n_rows_total": len(df),
        "schema": schema,
    }


if __name__ == "__main__":
    result = load_data_full()
    print(f"\nDone. data_source={result['data_source']} "
          f"n_rows_total={result['n_rows_total']:,} "
          f"n_features={len(result['feature_names'])} "
          f"n_classes={len(result['class_names'])}")
