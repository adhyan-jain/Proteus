"""Proteus Model Manager — Thread-safe in-memory model management with atomic hot-swapping
and double-buffering.

Guarantees:
- Zero-downtime in-memory model switching without process or container restart.
- Thread-safe prediction execution with atomic reference assignment under the GIL.
- In-flight inference requests complete safely on the old model reference.
- Automatic disk reload detection via active_release.json watcher.
"""
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import joblib
import numpy as np

from backend.release_manager import (
    DEFAULT_MODELS_DIR,
    get_active_release,
    set_active_release,
    validate_release_bundle,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("proteus.model_manager")


class ModelBundle:
    """Immutable in-memory bundle representing a loaded model release."""

    def __init__(
        self,
        clf: Any,
        schema: Dict[str, Any],
        encoder: Dict[str, Any],
        manifest: Dict[str, Any],
        release_version: str,
        loaded_at: float,
    ):
        self.clf = clf
        self.schema = schema
        self.encoder = encoder
        self.manifest = manifest
        self.release_version = release_version
        self.loaded_at = loaded_at
        self.feature_names = schema["feature_names"]
        self.class_names = schema["class_names"]
        self.n_features = schema["n_features"]
        self.n_classes = schema["n_classes"]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(X)


class ModelManager:
    """Thread-safe manager for active model inference, atomic hot-swapping, and version observability."""

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or DEFAULT_MODELS_DIR
        self._active_bundle: Optional[ModelBundle] = None
        self._swap_lock = threading.Lock()
        self._last_active_mtime: Optional[float] = None
        self._load_active_initial()

    def _load_active_initial(self):
        """Perform initial load of active release on startup."""
        active_meta = get_active_release(self.models_dir)
        version_to_load = active_meta.get("active_version", "v001") if active_meta else "v001"

        try:
            self._swap_to_version_internal(version_to_load)
        except Exception as e:
            log.warning(f"Could not load release {version_to_load} initially: {e}. Falling back to default models/ directory.")
            self._fallback_load_root()

    def _fallback_load_root(self):
        """Fallback loader reading raw artifacts directly from models/ root."""
        model_path = self.models_dir / "baseline_rf.joblib"
        schema_path = self.models_dir / "feature_schema.json"
        encoder_path = self.models_dir / "label_encoder.json"
        manifest_path = self.models_dir / "manifest.json"

        if model_path.exists() and schema_path.exists():
            try:
                clf = joblib.load(model_path)
                with open(schema_path, "r") as f:
                    schema = json.load(f)
                encoder = {}
                if encoder_path.exists():
                    with open(encoder_path, "r") as f:
                        encoder = json.load(f)
                manifest = {}
                if manifest_path.exists():
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)

                self._active_bundle = ModelBundle(
                    clf=clf,
                    schema=schema,
                    encoder=encoder,
                    manifest=manifest,
                    release_version="v001",
                    loaded_at=time.time(),
                )
                log.info("Loaded fallback model bundle from models root successfully.")
            except Exception as e:
                log.error(f"Fallback model loading failed: {e}")

    def _swap_to_version_internal(self, version_name: str) -> ModelBundle:
        """Internal helper to load and validate a release bundle in background before atomic swap."""
        releases_dir = self.models_dir / "releases"
        target_dir = releases_dir / version_name

        is_valid, reason, manifest = validate_release_bundle(target_dir)
        if not is_valid:
            raise ValueError(f"Release {version_name} failed integrity validation: {reason}")

        model_path = target_dir / "model.joblib"
        schema_path = target_dir / "feature_schema.json"
        encoder_path = target_dir / "label_encoder.json"

        # Load artifacts in background memory buffer (double-buffering)
        clf = joblib.load(model_path)
        with open(schema_path, "r") as f:
            schema = json.load(f)
        with open(encoder_path, "r") as f:
            encoder = json.load(f)

        # Pre-activation sanity test
        dummy_x = np.zeros((1, schema["n_features"]), dtype=np.float32)
        _ = clf.predict(dummy_x)
        _ = clf.predict_proba(dummy_x)

        new_bundle = ModelBundle(
            clf=clf,
            schema=schema,
            encoder=encoder,
            manifest=manifest or {},
            release_version=version_name,
            loaded_at=time.time(),
        )

        with self._swap_lock:
            # Atomic pointer replacement under Python GIL
            self._active_bundle = new_bundle
            active_file = self.models_dir / "active_release.json"
            if active_file.exists():
                self._last_active_mtime = active_file.stat().st_mtime

        log.info(f"Atomically swapped active model to release {version_name} (loaded in memory)")
        return new_bundle

    def get_bundle(self) -> Optional[ModelBundle]:
        """Get the currently active ModelBundle (zero-lock thread-safe read)."""
        return self._active_bundle

    def hot_swap_to_release(self, version_name: str, promote_on_disk: bool = True) -> ModelBundle:
        """Hot-swap the running in-memory model to the target release without downtime.

        Optionally updates active_release.json on disk.
        """
        if promote_on_disk:
            set_active_release(version_name, models_dir=self.models_dir)
        return self._swap_to_version_internal(version_name)

    def check_and_reload_if_updated(self) -> bool:
        """Poll active_release.json to see if a new release was activated on disk; hot-swaps if so."""
        active_file = self.models_dir / "active_release.json"
        if not active_file.exists():
            return False

        current_mtime = active_file.stat().st_mtime
        if self._last_active_mtime is None or current_mtime > self._last_active_mtime:
            active_meta = get_active_release(self.models_dir)
            if active_meta:
                new_ver = active_meta.get("active_version")
                current_ver = self._active_bundle.release_version if self._active_bundle else None
                if new_ver and new_ver != current_ver:
                    log.info(f"Detected disk pointer update from {current_ver} -> {new_ver}. Initiating hot swap...")
                    try:
                        self._swap_to_version_internal(new_ver)
                        return True
                    except Exception as e:
                        log.error(f"Auto hot-swap failed for release {new_ver}: {e}")
        return False
