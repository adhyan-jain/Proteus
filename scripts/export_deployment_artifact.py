"""Export production deployment model artifacts with schema, manifest, and verification hash.

Creates:
- models/releases/{version}/model.joblib
- models/releases/{version}/feature_schema.json
- models/releases/{version}/label_encoder.json
- models/releases/{version}/manifest.json
- models/active_release.json (Pointer to currently active release)
"""
import argparse
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
RELEASES_DIR = MODELS_DIR / "releases"
ACTIVE_FILE = MODELS_DIR / "active_release.json"

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_next_version() -> str:
    if not RELEASES_DIR.exists():
        return "v001"
    existing = [d.name for d in RELEASES_DIR.iterdir() if d.is_dir() and d.name.startswith("v")]
    if not existing:
        return "v001"
    numbers = []
    for e in existing:
        try:
            numbers.append(int(e[1:]))
        except ValueError:
            pass
    next_num = max(numbers, default=0) + 1
    return f"v{next_num:03d}"

def export_artifacts(version: str = None, n_samples: int = 5000, promote: bool = True):
    if version is None:
        version = get_next_version()
        
    release_dir = RELEASES_DIR / version
    release_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    # Paths in release directory
    model_path = release_dir / "model.joblib"
    schema_path = release_dir / "feature_schema.json"
    encoder_path = release_dir / "label_encoder.json"
    manifest_path = release_dir / "manifest.json"
    
    # Also mirror to root models/ for backward compatibility
    root_model_path = MODELS_DIR / "baseline_rf.joblib"
    root_schema_path = MODELS_DIR / "feature_schema.json"
    root_encoder_path = MODELS_DIR / "label_encoder.json"
    root_manifest_path = MODELS_DIR / "manifest.json"
    
    # Save model weights
    log.info(f"Serializing model to {model_path}...")
    joblib.dump(clf, model_path, compress=3)
    joblib.dump(clf, root_model_path, compress=3)
    
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
    with open(root_schema_path, "w") as f:
        json.dump(schema, f, indent=2)
        
    # Save label encoder map
    label_map = {
        "index_to_label": {i: name for i, name in enumerate(class_names)},
        "label_to_index": {name: i for i, name in enumerate(class_names)},
        "classes": class_names
    }
    with open(encoder_path, "w") as f:
        json.dump(label_map, f, indent=2)
    with open(root_encoder_path, "w") as f:
        json.dump(label_map, f, indent=2)
        
    # Calculate checksums
    model_sha256 = compute_sha256(model_path)
    schema_sha256 = compute_sha256(schema_path)
    encoder_sha256 = compute_sha256(encoder_path)
    
    # Save Manifest
    manifest = {
        "release_version": version,
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
                "file": "model.joblib",
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
    with open(root_manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        
    if promote:
        active_payload = {
            "active_version": version,
            "release_path": str(release_dir.relative_to(MODELS_DIR.parent)),
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "manifest": manifest
        }
        with open(ACTIVE_FILE, "w") as f:
            json.dump(active_payload, f, indent=2)
        log.info(f"Promoted release {version} as active release in {ACTIVE_FILE}")
        
    log.info(f"Model deployment artifacts exported successfully to {release_dir}")
    log.info(f"Model sha256: {model_sha256}")

def main():
    parser = argparse.ArgumentParser(description="Export versioned deployment model artifacts")
    parser.add_argument("--version", type=str, default=None, help="Release version string (e.g. v001)")
    parser.add_argument("--samples", type=int, default=5000, help="Number of training samples")
    parser.add_argument("--no-promote", action="store_true", help="Do not automatically activate this release")
    
    args = parser.parse_args()
    export_artifacts(version=args.version, n_samples=args.samples, promote=not args.no_promote)

if __name__ == "__main__":
    main()
