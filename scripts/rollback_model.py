"""Model Release Management & Rollback CLI.

Allows inspecting available model releases, switching the active model version,
or rolling back to a previous verified release.

Usage:
    python scripts/rollback_model.py --list
    python scripts/rollback_model.py --version v001
    python scripts/rollback_model.py --rollback-previous
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from proteus.release_manager import (
    DEFAULT_MODELS_DIR,
    get_active_release,
    list_releases,
    rollback_release,
    set_active_release,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rollback_model")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

def rollback_to_previous(models_dir: Optional[Path] = None):
    """Backward-compatible wrapper for rollback_release."""
    active_ver, rolled_back_to = rollback_release(models_dir=models_dir or MODELS_DIR)
    return active_ver != rolled_back_to


def main():
    parser = argparse.ArgumentParser(description="Model Release Management & Rollback CLI")
    parser.add_argument("--list", action="store_true", help="List all available model releases")
    parser.add_argument("--version", type=str, help="Activate a specific release version (e.g. v001)")
    parser.add_argument("--rollback-previous", action="store_true", help="Rollback to immediately preceding release version")
    
    args = parser.parse_args()
    
    if args.list:
        active = get_active_release(MODELS_DIR)
        active_ver = active.get("active_version") if active else "None"
        releases = list_releases(MODELS_DIR)
        print(f"\nActive Release: {active_ver}\n")
        print("Available Releases:")
        for r in releases:
            marker = " -> [ACTIVE]" if r["version"] == active_ver else ""
            print(f"  • {r['version']}: {r['model_type']} (created: {r['created_at']}, dataset: {r['dataset']}){marker}")
        print()
    elif args.version:
        set_active_release(args.version, models_dir=MODELS_DIR)
        log.info(f"Successfully activated release: {args.version}")
    elif args.rollback_previous:
        active_ver, rolled_back_to = rollback_release(models_dir=MODELS_DIR)
        log.info(f"Successfully rolled back from {active_ver} -> {rolled_back_to}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

