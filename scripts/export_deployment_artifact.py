"""Export production deployment model artifacts with schema, manifest, and verification hash.

Creates:
- models/baseline_rf.joblib (Trained RandomForest model)
- models/feature_schema.json (Ordered feature list, types, dimension)
- models/label_encoder.json (Mapping of class index to class name)
- models/manifest.json (Version, provenance, parameter specs, sha256 checksums)
"""
import hashlib
import json
import logging
from pathlib import Path
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from proteus.data import _generate_synthetic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("export_deployment_artifact")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def export_artifacts(n_samples: int = 5000):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
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
    
    log.info(f"Training production reference Random Forest ({len(X)} samples, {n_features} features, {len(class_names)} classes)...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42, n_jobs=-1)
    clf.fit(X.values, y)
    
    # Paths
    model_path = MODELS_DIR / "baseline_rf.joblib"
    schema_path = MODELS_DIR / "feature_schema.json"
    encoder_path = MODELS_DIR / "label_encoder.json"
    manifest_path = MODELS_DIR / "manifest.json"
    
    # Save model weights
    log.info(f"Serializing model to {model_path}...")
    joblib.dump(clf, model_path, compress=3)
    
    # Save schema
    schema = {
        "n_features": n_features,
        "feature_names": feature_names,
        "n_classes": len(class_names),
        "class_names": class_names,
        "input_dtype": "float32"
    }
    with open(schema_path, "w") as f:
        json.dump(schema, f, indent=2)
        
    # Save label encoder map
    label_map = {
        "index_to_label": {i: name for i, name in enumerate(class_names)},
        "label_to_index": {name: i for i, name in enumerate(class_names)},
        "classes": class_names
    }
    with open(encoder_path, "w") as f:
        json.dump(label_map, f, indent=2)
        
    # Calculate checksums
    model_sha256 = compute_sha256(model_path)
    schema_sha256 = compute_sha256(schema_path)
    encoder_sha256 = compute_sha256(encoder_path)
    
    # Save Manifest
    manifest = {
        "version": "1.0.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_type": "RandomForestClassifier",
        "parameters": {
            "n_estimators": clf.n_estimators,
            "max_depth": clf.max_depth,
            "random_state": 42
        },
        "training_metadata": {
            "dataset": "NSL-KDD-Schema-Reference",
            "n_samples": int(len(X)),
            "n_features": int(n_features),
            "n_classes": int(len(class_names))
        },
        "artifacts": {
            "model": {
                "file": "baseline_rf.joblib",
                "sha256": model_sha256,
                "size_bytes": model_path.stat().st_size
            },
            "schema": {
                "file": "feature_schema.json",
                "sha256": schema_sha256
            },
            "label_encoder": {
                "file": "label_encoder.json",
                "sha256": encoder_sha256
            }
        }
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    log.info(f"Model deployment artifacts exported successfully to {MODELS_DIR}")
    log.info(f"Model sha256: {model_sha256}")

if __name__ == "__main__":
    export_artifacts()
