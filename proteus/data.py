"""Data pipeline: try NSL-KDD download, fall back to synthetic NSL-KDD-schema data."""
import io
import time
import urllib.request

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

RNG = np.random.default_rng(42)

NSLKDD_TRAIN_URLS = [
    "https://raw.githubusercontent.com/defcom17/NSL_KDD/master/KDDTrain%2B.txt",
]

# NSL-KDD 41-feature schema (41 features + label + difficulty)
NSLKDD_COLUMNS = [
    "duration", "protocol_type", "service", "flag", "src_bytes", "dst_bytes", "land",
    "wrong_fragment", "urgent", "hot", "num_failed_logins", "logged_in", "num_compromised",
    "root_shell", "su_attempted", "num_root", "num_file_creations", "num_shells",
    "num_access_files", "num_outbound_cmds", "is_host_login", "is_guest_login", "count",
    "srv_count", "serror_rate", "srv_serror_rate", "rerror_rate", "srv_rerror_rate",
    "same_srv_rate", "diff_srv_rate", "srv_diff_host_rate", "dst_host_count",
    "dst_host_srv_count", "dst_host_same_srv_rate", "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate", "dst_host_srv_diff_host_rate", "dst_host_serror_rate",
    "dst_host_srv_serror_rate", "dst_host_rerror_rate", "dst_host_srv_rerror_rate",
    "label", "difficulty",
]

ATTACK_TO_CLASS = {
    "normal": "benign",
    "neptune": "dos", "smurf": "dos", "back": "dos", "teardrop": "dos", "pod": "dos",
    "land": "dos", "apache2": "dos", "udpstorm": "dos", "processtable": "dos", "mailbomb": "dos",
    "satan": "probe", "ipsweep": "probe", "nmap": "probe", "portsweep": "probe",
    "mscan": "probe", "saint": "probe",
    "warezclient": "r2l", "guess_passwd": "r2l", "warezmaster": "r2l", "imap": "r2l",
    "ftp_write": "r2l", "multihop": "r2l", "phf": "r2l", "spy": "r2l",
    "xlock": "r2l", "xsnoop": "r2l", "snmpguess": "r2l", "snmpgetattack": "r2l",
    "httptunnel": "r2l", "sendmail": "r2l", "named": "r2l", "worm": "r2l",
    "buffer_overflow": "u2r", "loadmodule": "u2r", "rootkit": "u2r", "perl": "u2r",
    "sqlattack": "u2r", "xterm": "u2r", "ps": "u2r",
}


def _try_download(timeout_s=15):
    for url in NSLKDD_TRAIN_URLS:
        try:
            t0 = time.time()
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                raw = resp.read()
            if time.time() - t0 > timeout_s:
                continue
            df = pd.read_csv(io.BytesIO(raw), names=NSLKDD_COLUMNS)
            if len(df) < 1000:
                continue
            return df
        except Exception:
            continue
    return None


def _generate_synthetic(n=6000):
    """Synthetic NSL-KDD-schema dataset with realistic class imbalance."""
    classes = {
        "benign": 0.60,
        "dos": 0.25,
        "probe": 0.12,
        "r2l": 0.015,
        "u2r": 0.015,
    }
    n_per = {c: max(5, int(n * p)) for c, p in classes.items()}
    rows = []
    numeric_cols = [c for c in NSLKDD_COLUMNS if c not in
                    ("protocol_type", "service", "flag", "label", "difficulty")]
    protos = ["tcp", "udp", "icmp"]
    services = ["http", "ftp", "smtp", "telnet", "private", "domain_u", "other"]
    flags = ["SF", "S0", "REJ", "RSTO"]

    # each class gets a distinct-but-overlapping feature-mean vector so the problem is
    # realistically hard (not trivially separable) -- gives drift room to actually hurt
    # accuracy, and gives the augmentation/retraining mechanisms room to help.
    class_means = {c: RNG.uniform(0, 1.6, size=len(numeric_cols)) * (i + 1)
                    for i, c in enumerate(classes)}

    for cls, cnt in n_per.items():
        mean = class_means[cls]
        for _ in range(cnt):
            vals = RNG.normal(loc=mean, scale=0.9 + mean * 0.35)
            vals = np.clip(vals, 0, None)
            row = dict(zip(numeric_cols, vals))
            row["protocol_type"] = RNG.choice(protos, p=[0.6, 0.3, 0.1])
            row["service"] = RNG.choice(services)
            row["flag"] = RNG.choice(flags)
            row["label"] = cls
            row["difficulty"] = RNG.integers(1, 21)
            rows.append(row)
    df = pd.DataFrame(rows)
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    return df


def load_data(n_synthetic=6000):
    """Returns dict with X_train, X_test, y_train, y_test, feature_names, class_names,
    label_encoder, data_source."""
    df = _try_download()
    if df is not None:
        source = "nsl-kdd-download"
        df["class"] = df["label"].str.strip().str.lower().map(
            lambda x: ATTACK_TO_CLASS.get(x, "other"))
        df = df.drop(columns=["label", "difficulty"])
    else:
        source = "synthetic-fallback"
        df = _generate_synthetic(n=n_synthetic)
        df["class"] = df["label"]
        df = df.drop(columns=["label", "difficulty"])

    cat_cols = ["protocol_type", "service", "flag"]
    df = pd.get_dummies(df, columns=cat_cols)

    le = LabelEncoder()
    y = le.fit_transform(df["class"])
    X = df.drop(columns=["class"]).astype(float)

    class_dist = df["class"].value_counts().to_dict()

    X_train, X_test, y_train, y_test = train_test_split(
        X.values, y, test_size=0.25, stratify=y, random_state=42)

    return {
        "X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test,
        "feature_names": list(X.columns), "class_names": list(le.classes_),
        "label_encoder": le, "data_source": source, "class_distribution": class_dist,
        "full_df": df,
    }
