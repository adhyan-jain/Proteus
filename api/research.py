"""Read-only research-artifact endpoints for the Next.js console (SPEC v1.3 P0 / v1.4 P1+).

Every response is a verbatim view of a file under results/ (plus its SHA-256, size and mtime), so
every number the UI shows traces to an artifact on disk. Nothing is computed, estimated or filled in
here. Non-finite floats are stored in the artifacts as {"__nonfinite__": "nan"}; they are returned as
null ("not measurable"), never as a number. Missing artifacts resolve to {available: false, reason}.
"""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
router = APIRouter(prefix="/api/research")

ARTIFACTS = {
    "p0_summary": "intervention_p0_S1_summary.json",
    "p0_b25": "intervention_p0_S1_B25.json",
    "p0_b100": "intervention_p0_S1_B100.json",
    "p1_summary": "intervention_p1_S1_B100_summary.json",
    "p1_decisions": "intervention_p1_S1_B100_decisions.json",
    "p2": "intervention_p2_S1_B100_summary.json",
    "s2_p0_summary": "intervention_p0_S2_summary.json",
    "p3_s2": "intervention_p3_S2_summary.json",
    "verification": "verification_report.json",
}


def _clean(obj):
    if isinstance(obj, dict):
        if set(obj) == {"__nonfinite__"}:
            return None
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(key: str):
    path = RESULTS / ARTIFACTS[key]
    if not path.exists():
        return None, {"available": False, "reason": f"{ARTIFACTS[key]} does not exist: that stage has "
                                                    f"not been run on this machine."}
    return _clean(json.loads(path.read_text())), None


def _artifact(key: str):
    path = RESULTS / ARTIFACTS[key]
    return {"file": f"results/{ARTIFACTS[key]}", "sha256": _sha(path), "bytes": path.stat().st_size,
            "modified": path.stat().st_mtime}


@router.get("/artifacts")
def artifacts():
    rows = []
    for key, name in ARTIFACTS.items():
        path = RESULTS / name
        rows.append({"key": key, "file": f"results/{name}", "exists": path.exists(),
                     **({"sha256": _sha(path), "bytes": path.stat().st_size} if path.exists() else {})})
    seeds = sorted(p.name for p in (RESULTS / "p1").glob("intervention_p1_S1_B100_seed*.json")) \
        if (RESULTS / "p1").exists() else []
    return {"available": True, "artifacts": rows, "p1_seed_files": seeds}


def _slim_p0(doc):
    data = doc.get("data", {})
    cache = data.get("cache") or {}
    slim = {k: v for k, v in doc.items() if k not in ("data", "criteria", "params")}
    slim["data"] = {"n_rows": data.get("n_rows"), "n_features": data.get("n_features"),
                    "class_names": cache.get("class_names"), "class_counts": cache.get("class_counts"),
                    "rows_per_day": cache.get("rows_per_day"),
                    "label_conflicts": data.get("label_conflicts_diagnostic_only")}
    slim["criteria"] = doc.get("criteria")
    slim["params"] = doc.get("params")
    return slim


@router.get("/p0")
def p0():
    doc, err = _load("p0_summary")
    if err:
        return err
    return {"available": True, "artifact": _artifact("p0_summary"), "doc": _slim_p0(doc)}


@router.get("/p0/s2")
def p0_s2():
    """The S2 P0 gate that decides whether P3 may run (same frozen section-L.1 rules)."""
    doc, err = _load("s2_p0_summary")
    if err:
        return err
    return {"available": True, "artifact": _artifact("s2_p0_summary"), "doc": _slim_p0(doc)}


@router.get("/p1")
def p1():
    doc, err = _load("p1_summary")
    if err:
        return err
    return {"available": True, "artifact": _artifact("p1_summary"), "doc": doc}


@router.get("/p1/decisions")
def p1_decisions():
    doc, err = _load("p1_decisions")
    if err:
        return err
    return {"available": True, "artifact": _artifact("p1_decisions"), "doc": doc}


@router.get("/verification")
def verification():
    doc, err = _load("verification")
    if err:
        return err
    return {"available": True, "artifact": _artifact("verification"), "doc": doc}


@router.get("/stages")
def stages():
    """Which stages of the gated pipeline exist on disk (P2/P3 only run if their gate opened)."""
    out = {}
    for key, label in (("p0_summary", "P0 (S1)"), ("p1_summary", "P1 campaign"),
                       ("p2", "P2 (WGAN-GP generator)"), ("s2_p0_summary", "S2 P0 gate"),
                       ("p3_s2", "P3 (S2 replication)")):
        doc, err = _load(key)
        out[key] = {"label": label, "ran": err is None, **({"artifact": _artifact(key)} if err is None else {})}
    p1_doc, _ = _load("p1_summary")
    out["gates"] = {"p2_unlocked": (p1_doc or {}).get("verdict", {}).get("p2_unlocked"),
                    "p1_branch": (p1_doc or {}).get("verdict", {}).get("branch")}
    return {"available": True, "stages": out}
