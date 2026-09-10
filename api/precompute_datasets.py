"""Precompute a small JSON summary of the full-scale datasets so the API never has to
reload multi-GB CSVs per request. Run manually: .venv/bin/python api/precompute_datasets.py
Writes api/cache/datasets_summary.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proteus import data_full  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
OUT = CACHE_DIR / "datasets_summary.json"


def summarize(name, loader):
    t0 = time.time()
    try:
        d = loader()
    except Exception as e:
        return {
            "name": name,
            "available": False,
            "error": str(e),
        }
    elapsed = time.time() - t0
    return {
        "name": name,
        "available": True,
        "data_source": d["data_source"],
        "n_rows_total": d["n_rows_total"],
        "n_features": len(d["feature_names"]),
        "class_names": d["class_names"],
        "class_distribution": {str(k): int(v) for k, v in d["class_distribution"].items()},
        "split_sizes": {
            "train": int(len(d["y_train"])),
            "val": int(len(d["y_val"])),
            "test": int(len(d["y_test"])),
        },
        "feature_columns": d["feature_names"],
        "schema": {
            "label_column": d["schema"]["label_column"],
            "categorical_columns": d["schema"]["categorical_columns"],
            "identifier_columns": d["schema"]["identifier_columns"],
        },
        "load_seconds": round(elapsed, 1),
    }


def main():
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasets": [],
    }
    print("Loading CICIDS2017 (full)...")
    summary["datasets"].append(summarize("cicids2017-wtmc2021-corrected", data_full.load_data_full))
    print("Loading InSDN...")
    summary["datasets"].append(summarize("insdn", data_full.load_insdn))

    OUT.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
