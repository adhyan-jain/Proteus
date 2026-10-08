"""Run the verification commands and record their REAL outputs in results/verification_report.json.

    .venv/bin/python scripts/write_verification_report.py [--skip-frontend] [--only-fast]

Nothing is estimated: each entry stores the command, its exit code and the last lines of its output;
pytest counts are parsed from pytest's own summary line.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from proteus.intervention.provenance import git_state, utc_now_iso  # noqa: E402
from proteus.intervention.serialize import write_json  # noqa: E402


def run(cmd, cwd=ROOT, timeout=3 * 3600):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode, out, round(time.time() - t0, 1)


def pytest_entry(cmd):
    rc, out, secs = run(cmd)
    summary = next((ln for ln in reversed(out) if re.search(r"\d+ (passed|failed|error)", ln)), "")
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|error|errors|warnings?)", summary)}
    return {"command": cmd, "exit_code": rc, "result": f"{summary.strip('= ')} (wall {secs}s)",
            "passed": counts.get("passed"), "failed": counts.get("failed", 0) + counts.get("error", 0)
            + counts.get("errors", 0), "skipped": counts.get("skipped", 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true")
    ap.add_argument("--only-fast", action="store_true", help="skip the full suite")
    args = ap.parse_args()
    cmds = []
    cmds.append(pytest_entry(".venv/bin/python -m pytest -q tests/test_intervention_generators.py "
                             "tests/test_intervention_controller.py tests/test_intervention_gate14.py "
                             "tests/test_intervention_p1.py tests/test_intervention_analyze_p1.py "
                             "tests/test_intervention_p0_s2.py tests/test_research_api.py"))
    if not args.only_fast:
        cmds.append(pytest_entry(".venv/bin/python -m pytest -q"))
    if not args.skip_frontend:
        for cmd in ("npx tsc --noEmit", "npm run build"):
            rc, out, secs = run(cmd, cwd=ROOT / "frontend")
            cmds.append({"command": f"(frontend) {cmd}", "exit_code": rc, "passed": None, "failed": None,
                         "skipped": None, "result": f"exit {rc} (wall {secs}s): {' | '.join(out[-3:])}"})
    doc = {"kind": "verification_report", "generated_utc": utc_now_iso(), **git_state(),
           "commands": cmds,
           "notes": ["Counts are parsed from the tools' own output; the working tree may differ from "
                     "git_sha (git_dirty) because results are committed after verification."]}
    write_json(ROOT / "results" / "verification_report.json", doc)
    print(json.dumps([{k: c[k] for k in ("command", "exit_code", "result")} for c in cmds], indent=1))


if __name__ == "__main__":
    main()
