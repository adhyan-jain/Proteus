"""Model Release Management & Rollback CLI.

Allows inspecting available model releases, switching the active model version,
or rolling back to a previous verified release.

Usage:
    python scripts/rollback_model.py --list
    python scripts/rollback_model.py --version v001
    python scripts/rollback_model.py --rollback-previous
"""
import argparse
import json
import logging
from pathlib import Path
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rollback_model")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RELEASES_DIR = MODELS_DIR / "releases"
ACTIVE_FILE = MODELS_DIR / "active_release.json"

def list_releases():
    if not RELEASES_DIR.exists():
        log.warning("No releases directory found in models/")
        return []
    
    releases = []
    for rdir in sorted(RELEASES_DIR.iterdir()):
        if rdir.is_dir():
            manifest_file = rdir / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r") as f:
                        manifest = json.load(f)
                    releases.append({
                        "version": rdir.name,
                        "path": str(rdir),
                        "created_at": manifest.get("created_at"),
                        "model_type": manifest.get("model_type"),
                        "dataset": manifest.get("training_metadata", {}).get("dataset"),
                    })
                except Exception as e:
                    log.error(f"Error reading manifest in {rdir}: {e}")
    return releases

def get_active_release():
    if not ACTIVE_FILE.exists():
        return None
    try:
        with open(ACTIVE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error reading active_release.json: {e}")
        return None

def set_active_release(version_name: str):
    target_dir = RELEASES_DIR / version_name
    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError(f"Release version '{version_name}' not found in {RELEASES_DIR}")
    
    manifest_file = target_dir / "manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"manifest.json missing in release {version_name}")
        
    with open(manifest_file, "r") as f:
        manifest = json.load(f)
        
    active_payload = {
        "active_version": version_name,
        "release_path": str(target_dir.relative_to(MODELS_DIR.parent)),
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": manifest
    }
    
    with open(ACTIVE_FILE, "w") as f:
        json.dump(active_payload, f, indent=2)
        
    log.info(f"Successfully activated model release: {version_name}")
    log.info(f"Model Type: {manifest.get('model_type')}, Version: {manifest.get('version')}")

def rollback_to_previous():
    active = get_active_release()
    releases = list_releases()
    if not releases:
        log.error("No releases available to rollback to.")
        return False
        
    if not active:
        log.info(f"No active release set. Activating latest release: {releases[-1]['version']}")
        set_active_release(releases[-1]["version"])
        return True
        
    current_ver = active.get("active_version")
    ver_list = [r["version"] for r in releases]
    if current_ver not in ver_list:
        log.warning(f"Current version '{current_ver}' not in releases list. Activating latest: {releases[-1]['version']}")
        set_active_release(releases[-1]["version"])
        return True
        
    cur_idx = ver_list.index(current_ver)
    if cur_idx == 0:
        log.warning(f"Active release '{current_ver}' is already the oldest available release.")
        return False
        
    prev_ver = ver_list[cur_idx - 1]
    log.info(f"Rolling back from {current_ver} -> {prev_ver}...")
    set_active_release(prev_ver)
    return True

def main():
    parser = argparse.ArgumentParser(description="Model Release Management & Rollback CLI")
    parser.add_argument("--list", action="store_true", help="List all available model releases")
    parser.add_argument("--version", type=str, help="Activate a specific release version (e.g. v001)")
    parser.add_argument("--rollback-previous", action="store_true", help="Rollback to immediately preceding release version")
    
    args = parser.parse_args()
    
    if args.list:
        active = get_active_release()
        active_ver = active.get("active_version") if active else "None"
        releases = list_releases()
        print(f"\nActive Release: {active_ver}\n")
        print("Available Releases:")
        for r in releases:
            marker = " -> [ACTIVE]" if r["version"] == active_ver else ""
            print(f"  • {r['version']}: {r['model_type']} (created: {r['created_at']}, dataset: {r['dataset']}){marker}")
        print()
    elif args.version:
        set_active_release(args.version)
    elif args.rollback_previous:
        rollback_to_previous()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
