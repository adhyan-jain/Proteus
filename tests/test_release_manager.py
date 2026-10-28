"""Unit & integration tests for backend.release_manager."""
import json
import shutil
from pathlib import Path
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from backend.release_manager import (
    compute_sha256,
    get_next_version,
    package_release,
    validate_release_bundle,
    get_active_release,
    set_active_release,
    rollback_release,
    list_releases,
)


@pytest.fixture
def temp_models_dir(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def test_compute_sha256(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("proteus-test-content")
    sha = compute_sha256(f)
    assert isinstance(sha, str)
    assert len(sha) == 64


def test_get_next_version(temp_models_dir):
    assert get_next_version(temp_models_dir) == "v001"
    
    (temp_models_dir / "releases" / "v001").mkdir(parents=True)
    assert get_next_version(temp_models_dir) == "v002"
    
    (temp_models_dir / "releases" / "v005").mkdir(parents=True)
    assert get_next_version(temp_models_dir) == "v006"


def test_package_and_validate_release(temp_models_dir):
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    X = np.random.randn(20, 4).astype(np.float32)
    y = np.random.choice([0, 1], size=20)
    clf.fit(X, y)

    feature_names = ["f1", "f2", "f3", "f4"]
    class_names = ["benign", "attack"]

    version_str, release_dir, manifest = package_release(
        clf=clf,
        feature_names=feature_names,
        class_names=class_names,
        version_str="v001",
        training_metadata={"test": True},
        models_dir=temp_models_dir,
        promote=True,
    )

    assert version_str == "v001"
    assert release_dir.exists()
    assert (release_dir / "model.joblib").exists()
    assert (release_dir / "feature_schema.json").exists()
    assert (release_dir / "label_encoder.json").exists()
    assert (release_dir / "manifest.json").exists()

    # Validate bundle
    is_valid, reason, mf = validate_release_bundle(release_dir)
    assert is_valid is True
    assert mf["release_version"] == "v001"

    # Active pointer check
    active = get_active_release(temp_models_dir)
    assert active["active_version"] == "v001"


def test_release_rollback(temp_models_dir):
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    X = np.random.randn(20, 4).astype(np.float32)
    y = np.random.choice([0, 1], size=20)
    clf.fit(X, y)

    # Package v001 and v002
    package_release(clf, ["f1", "f2", "f3", "f4"], ["0", "1"], "v001", {}, temp_models_dir, promote=True)
    package_release(clf, ["f1", "f2", "f3", "f4"], ["0", "1"], "v002", {}, temp_models_dir, promote=True)

    assert get_active_release(temp_models_dir)["active_version"] == "v002"

    active_ver, rolled_back_to = rollback_release(temp_models_dir)
    assert active_ver == "v002"
    assert rolled_back_to == "v001"
    assert get_active_release(temp_models_dir)["active_version"] == "v001"
