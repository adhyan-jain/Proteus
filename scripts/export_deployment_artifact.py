"""Export production deployment model artifacts with schema, manifest, and verification hash.

Creates:
- models/releases/{version}/model.joblib
- models/releases/{version}/feature_schema.json
- models/releases/{version}/label_encoder.json
- models/releases/{version}/manifest.json
- models/active_release.json (Pointer to currently active release)
"""
import argparse
import logging
import sys
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from backend.data import _generate_synthetic
from backend.release_manager import (
    DEFAULT_MODELS_DIR,
    get_next_version,
    package_release,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("export_deployment_artifact")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def export_artifacts(version: str = None, n_samples: int = 5000, promote: bool = True):
    if version is None:
        version = get_next_version(MODELS_DIR)
        
    log.info(f"Generating deterministic reference training data ({n_samples} samples)...")
    df = _generate_synthetic(n=n_samples)
    df["class"] = df["label"]
    df = df.drop(columns=["label", "difficulty"])
    df = pd.get_dummies(df, columns=["protocol_type", "service", "flag"])
    
    le = LabelEncoder()
    y = le.fit_transform(df["class"])
    X = df.drop(columns=["class"]).astype(np.float32)
    feature_names = list(X.columns)
    class_names = list(le.classes_)
    n_features = len(feature_names)
    
    log.info(f"Training production reference Random Forest for release {version} ({len(X)} samples, {n_features} features, {len(class_names)} classes)...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42, n_jobs=-1)
    clf.fit(X.values, y)
    
    training_meta = {
        "dataset": "NSL-KDD-Schema-Reference",
        "n_samples": int(len(X)),
        "n_features": int(n_features),
        "n_classes": int(len(class_names)),
        "parameters": {
            "n_estimators": clf.n_estimators,
            "max_depth": clf.max_depth,
            "random_state": 42,
        },
    }
    
    version_out, release_dir, manifest = package_release(
        clf=clf,
        feature_names=feature_names,
        class_names=class_names,
        version_str=version,
        training_metadata=training_meta,
        models_dir=MODELS_DIR,
        promote=promote,
    )
    
    log.info(f"Model deployment artifacts exported successfully to {release_dir}")
    log.info(f"Model sha256: {manifest['artifacts']['model']['sha256']}")
    return version_out, release_dir, manifest


def main():
    parser = argparse.ArgumentParser(description="Export versioned deployment model artifacts")
    parser.add_argument("--version", type=str, default=None, help="Release version string (e.g. v001)")
    parser.add_argument("--samples", type=int, default=5000, help="Number of training samples")
    parser.add_argument("--no-promote", action="store_true", help="Do not automatically activate this release")
    
    args = parser.parse_args()
    export_artifacts(version=args.version, n_samples=args.samples, promote=not args.no_promote)


if __name__ == "__main__":
    main()

