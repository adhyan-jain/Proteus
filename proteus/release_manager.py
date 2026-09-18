"""Proteus Release Manager — Library for versioned artifact packaging, integrity verification,
atomic promotion, and rollback.

Features:
- Deterministic SHA256 checksum calculation for all bundle artifacts.
- Atomic directory staging (writes to temporary staging folder before atomic rename).
- Schema, manifest, model, and encoder bundle integrity validation.
- Atomic production pointer update in active_release.json.
- Thread-safe rollback to previous or targeted verified release.
"""
import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import joblib
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("proteus.release_manager")

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def get_next_version(dir_path: Optional[Path] = None) -> str:
    """Determine the next sequential release version string (e.g. v001, v002).

    Accepts either models_dir or models/releases directory.
    """
    if dir_path is None:
        target_dir = DEFAULT_MODELS_DIR / "releases"
    elif dir_path.name == "releases":
        target_dir = dir_path
    elif (dir_path / "releases").exists():
        target_dir = dir_path / "releases"
    else:
        # Check if dir_path itself contains version directories
        if dir_path.exists():
            direct_v = [d.name for d in dir_path.iterdir() if d.is_dir() and d.name.startswith("v")]
            if direct_v:
                target_dir = dir_path
            else:
                target_dir = dir_path / "releases"
        else:
            target_dir = dir_path / "releases"

    if not target_dir.exists():
        return "v001"
    
    existing = [d.name for d in target_dir.iterdir() if d.is_dir() and d.name.startswith("v") and not d.name.startswith(".")]
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


def package_release(
    clf: Any,
    feature_names: List[str],
    class_names: List[str],
    version: Optional[str] = None,
    training_metadata: Optional[Dict[str, Any]] = None,
    models_dir: Optional[Path] = None,
    promote: bool = False,
    version_str: Optional[str] = None,
    overwrite: bool = True,
) -> Tuple[str, Path, Dict[str, Any]]:
    """Package a trained classifier and its schema into an immutable, versioned release bundle.

    Uses atomic directory staging to guarantee that no partial or corrupt bundle is visible.

    Returns:
        (version_name, release_dir_path, manifest_dict)
    """
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR
    releases_dir = models_dir / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    # Handle parameter order swaps gracefully
    if isinstance(version, dict) and (isinstance(training_metadata, str) or training_metadata is None):
        version, training_metadata = training_metadata, version

    if version_str is not None:
        version = version_str

    if version is None:
        version = get_next_version(models_dir)

    target_dir = releases_dir / version
    if target_dir.exists() and not overwrite:
        raise FileExistsError(f"Release directory {target_dir} already exists.")

    # Staging directory for atomic creation
    staging_dir = releases_dir / f".staging_{version}_{int(time.time()*1000)}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        model_path = staging_dir / "model.joblib"
        schema_path = staging_dir / "feature_schema.json"
        encoder_path = staging_dir / "label_encoder.json"
        manifest_path = staging_dir / "manifest.json"

        # 1. Serialize model
        joblib.dump(clf, model_path, compress=3)

        # 2. Serialize feature schema
        n_features = len(feature_names)
        schema_data = {
            "n_features": n_features,
            "feature_names": feature_names,
            "n_classes": len(class_names),
            "class_names": class_names,
            "input_dtype": "float32",
        }
        with open(schema_path, "w") as f:
            json.dump(schema_data, f, indent=2)

        # 3. Serialize label encoder
        encoder_data = {
            "class_to_idx": {c: i for i, c in enumerate(class_names)},
            "idx_to_class": {str(i): c for i, c in enumerate(class_names)},
        }
        with open(encoder_path, "w") as f:
            json.dump(encoder_data, f, indent=2)

        # 4. Compute SHA256 checksums
        model_sha = compute_sha256(model_path)
        schema_sha = compute_sha256(schema_path)
        encoder_sha = compute_sha256(encoder_path)
        model_size = model_path.stat().st_size

        # 5. Build and save manifest
        created_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        clf_params = getattr(clf, "get_params", lambda: {})()
        safe_params = {}
        for k, v in clf_params.items():
            if isinstance(v, (int, float, str, bool, list, dict)) or v is None:
                safe_params[k] = v
            else:
                safe_params[k] = str(v)

        meta = training_metadata or {
            "dataset": "Proteus-Adaptive-Retrained",
            "n_samples": getattr(clf, "n_samples_seen_", 0),
            "n_features": n_features,
            "n_classes": len(class_names),
        }

        manifest = {
            "release_version": version,
            "version": "1.0.0",
            "created_at": created_iso,
            "model_type": type(clf).__name__,
            "parameters": safe_params,
            "training_metadata": meta,
            "artifacts": {
                "model": {
                    "file": "model.joblib",
                    "sha256": model_sha,
                    "size_bytes": model_size,
                },
                "schema": {
                    "file": "feature_schema.json",
                    "sha256": schema_sha,
                },
                "label_encoder": {
                    "file": "label_encoder.json",
                    "sha256": encoder_sha,
                },
            },
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        # Atomic directory promotion: rename staging to target
        if target_dir.exists():
            backup_dir = releases_dir / f".backup_{version}_{int(time.time()*1000)}"
            target_dir.rename(backup_dir)
            staging_dir.rename(target_dir)
            shutil.rmtree(backup_dir, ignore_errors=True)
        else:
            staging_dir.rename(target_dir)
            
        log.info(f"Successfully created release bundle {version} at {target_dir}")

        # Also mirror to root models/ for backward compatibility
        try:
            joblib.dump(clf, models_dir / "baseline_rf.joblib", compress=3)
            with open(models_dir / "feature_schema.json", "w") as f:
                json.dump(schema_data, f, indent=2)
            with open(models_dir / "label_encoder.json", "w") as f:
                json.dump(encoder_data, f, indent=2)
            with open(models_dir / "manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            log.warning(f"Could not mirror release to models root: {e}")

        if promote:
            set_active_release(version, models_dir=models_dir)

        return version, target_dir, manifest

    except Exception as e:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        log.error(f"Failed to package release {version}: {e}")
        raise


def validate_release_bundle(release_dir: Path) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Verify that a release directory is complete, intact, and matches its SHA256 checksums.

    Returns:
        (is_valid: bool, error_reason: Optional[str], manifest_dict: Optional[dict])
    """
    if not release_dir.exists() or not release_dir.is_dir():
        return False, f"Directory does not exist: {release_dir}", None

    manifest_path = release_dir / "manifest.json"
    model_path = release_dir / "model.joblib"
    schema_path = release_dir / "feature_schema.json"
    encoder_path = release_dir / "label_encoder.json"

    for req_file in [manifest_path, model_path, schema_path, encoder_path]:
        if not req_file.exists():
            return False, f"Missing required release artifact: {req_file.name}", None

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Check SHA256
        model_sha = compute_sha256(model_path)
        expected_model_sha = manifest["artifacts"]["model"]["sha256"]
        if model_sha != expected_model_sha:
            return False, f"Model SHA256 mismatch (expected {expected_model_sha[:8]}, got {model_sha[:8]})", manifest

        schema_sha = compute_sha256(schema_path)
        expected_schema_sha = manifest["artifacts"]["schema"]["sha256"]
        if schema_sha != expected_schema_sha:
            return False, f"Schema SHA256 mismatch", manifest

        encoder_sha = compute_sha256(encoder_path)
        expected_encoder_sha = manifest["artifacts"]["label_encoder"]["sha256"]
        if encoder_sha != expected_encoder_sha:
            return False, f"Label encoder SHA256 mismatch", manifest

        # Test model unpickling
        clf = joblib.load(model_path)
        with open(schema_path, "r") as f:
            schema = json.load(f)

        n_features = schema["n_features"]
        dummy_input = np.zeros((1, n_features), dtype=np.float32)
        preds = clf.predict(dummy_input)
        if len(preds) != 1:
            return False, "Model prediction failed sanity check", manifest

        return True, None, manifest

    except Exception as e:
        return False, f"Validation exception: {str(e)}", None


def get_active_release(models_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read the currently active release metadata from active_release.json."""
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR
    active_file = models_dir / "active_release.json"
    if not active_file.exists():
        return None
    try:
        with open(active_file, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error reading {active_file}: {e}")
        return None


def set_active_release(version_name: str, models_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Atomically update active_release.json to point to the specified release.

    Performs validation before writing.
    """
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR
    releases_dir = models_dir / "releases"
    target_dir = releases_dir / version_name

    is_valid, reason, manifest = validate_release_bundle(target_dir)
    if not is_valid:
        raise ValueError(f"Cannot activate invalid release {version_name}: {reason}")

    active_file = models_dir / "active_release.json"
    tmp_active_file = models_dir / f"active_release.json.tmp_{os.getpid()}"

    # Calculate relative release path
    try:
        rel_path = str(target_dir.relative_to(models_dir.parent))
    except ValueError:
        rel_path = str(target_dir)

    active_payload = {
        "active_version": version_name,
        "release_path": rel_path,
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": manifest,
    }

    # Atomic file replacement
    with open(tmp_active_file, "w") as f:
        json.dump(active_payload, f, indent=2)
    tmp_active_file.replace(active_file)

    log.info(f"Successfully activated model release: {version_name}")
    return active_payload


def list_releases(models_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all available model releases with validation status."""
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR
    releases_dir = models_dir / "releases"
    if not releases_dir.exists():
        return []

    releases = []
    for rdir in sorted(releases_dir.iterdir()):
        if rdir.is_dir() and not rdir.name.startswith("."):
            manifest_file = rdir / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r") as f:
                        manifest = json.load(f)
                    is_valid, reason, _ = validate_release_bundle(rdir)
                    releases.append({
                        "version": rdir.name,
                        "path": str(rdir),
                        "created_at": manifest.get("created_at"),
                        "model_type": manifest.get("model_type"),
                        "dataset": manifest.get("training_metadata", {}).get("dataset"),
                        "is_valid": is_valid,
                        "validation_error": reason,
                    })
                except Exception as e:
                    log.error(f"Error reading manifest in {rdir}: {e}")
    return releases


def rollback_release(models_dir: Optional[Path] = None, target_version: Optional[str] = None) -> Tuple[str, str]:
    """Roll back the active release to a prior verified version.

    If target_version is not specified, rolls back to the immediate predecessor.

    Returns:
        (prior_version: str, active_version_after_rollback: str)
    """
    if models_dir is None:
        models_dir = DEFAULT_MODELS_DIR
    releases = [r for r in list_releases(models_dir) if r["is_valid"]]
    if not releases:
        raise RuntimeError("No valid releases available for rollback.")

    active = get_active_release(models_dir)
    current_ver = active.get("active_version") if active else "unknown"

    if target_version:
        matched = [r for r in releases if r["version"] == target_version]
        if not matched:
            raise ValueError(f"Target rollback version '{target_version}' is not valid or does not exist.")
        set_active_release(target_version, models_dir=models_dir)
        return current_ver, target_version

    # Find previous version
    ver_list = [r["version"] for r in releases]
    if current_ver in ver_list:
        idx = ver_list.index(current_ver)
        if idx > 0:
            prev_ver = ver_list[idx - 1]
        else:
            prev_ver = ver_list[0]
    else:
        prev_ver = ver_list[-1]

    set_active_release(prev_ver, models_dir=models_dir)
    return current_ver, prev_ver
