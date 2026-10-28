"""Compare regenerated result files with the committed ones. Usage: compare_results.py <regenerated_dir> [rtol]
Numbers must agree within rtol (default 1e-6, to allow GPU float non-determinism); everything else must be equal.
Exit status 1 if any file differs or is missing."""
import json
import math
import sys
from pathlib import Path

NEW, RTOL = Path(sys.argv[1]), float(sys.argv[2]) if len(sys.argv) > 2 else 1e-6
OLD = Path(__file__).resolve().parent.parent / "results"


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [f"{path}: keys differ"]
        return [d for k in a for d in diff(a[k], b[k], f"{path}/{k}")]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} vs {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return []
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return [] if math.isclose(a, b, rel_tol=RTOL, abs_tol=1e-9) else [f"{path}: {a} vs {b}"]
    return [] if a == b else [f"{path}: {a!r} vs {b!r}"]


bad = 0
for old in sorted(OLD.glob("*.json")):
    new = NEW / old.name
    if not new.exists():
        print("MISSING", old.name)
        bad += 1
        continue
    d = diff(json.loads(new.read_text()), json.loads(old.read_text()))
    print(("OK     " if not d else "DIFF   ") + old.name + ("" if not d else f" ({len(d)} differences, first: {d[0]})"))
    bad += bool(d)
sys.exit(1 if bad else 0)
