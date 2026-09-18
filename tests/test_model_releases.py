"""Tests for model release management, manifest verification, and rollback mechanism."""
import json
import pytest
from pathlib import Path
from scripts.export_deployment_artifact import export_artifacts
from scripts.rollback_model import list_releases, get_active_release, set_active_release, rollback_to_previous
from api.server import _load_model_artifacts, version

def test_release_export_and_metadata():
    # Export a test release
    test_ver = "v999"
    try:
        export_artifacts(version=test_ver, n_samples=1000, promote=True)
        
        # Verify active release
        active = get_active_release()
        assert active["active_version"] == test_ver
        
        # Verify files in release dir
        release_dir = Path("models/releases") / test_ver
        assert (release_dir / "model.joblib").exists()
        assert (release_dir / "feature_schema.json").exists()
        assert (release_dir / "label_encoder.json").exists()
        assert (release_dir / "manifest.json").exists()
        
        with open(release_dir / "manifest.json", "r") as f:
            manifest = json.load(f)
        assert manifest["release_version"] == test_ver
        assert "sha256" in manifest["artifacts"]["model"]
    finally:
        import shutil
        shutil.rmtree(Path("models/releases") / test_ver, ignore_errors=True)


def test_rollback_and_release_switching():
    # Ensure v001 exists
    export_artifacts(version="v001", n_samples=1000, promote=True)
    export_artifacts(version="v002", n_samples=1000, promote=True)
    
    # Active should be v002
    assert get_active_release()["active_version"] == "v002"
    
    # Rollback to v001
    res = rollback_to_previous()
    assert res is True
    assert get_active_release()["active_version"] == "v001"
    
    # Explicit switch to v002
    set_active_release("v002")
    assert get_active_release()["active_version"] == "v002"

def test_api_reloads_active_release():
    set_active_release("v001")
    mc = _load_model_artifacts(force_reload=True)
    assert mc["release_version"] == "v001"
    
    v = version()
    assert v["release_version"] == "v001"
