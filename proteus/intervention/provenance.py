"""Small provenance helpers shared by the cache builder and the P0 runner."""
import datetime
import platform
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          check=True).stdout


def git_state():
    """HEAD SHA plus whether the working tree differs from it (results from a dirty tree are not
    reproducible from the SHA alone, so the flag travels with every result file)."""
    try:
        sha = _git("rev-parse", "HEAD").strip()
        dirty = [line for line in _git("status", "--porcelain").splitlines() if line.strip()]
        return {"git_sha": sha, "git_dirty": bool(dirty), "git_dirty_files": len(dirty)}
    except (OSError, subprocess.CalledProcessError) as e:
        return {"git_sha": None, "git_dirty": None, "git_dirty_files": None,
                "git_error": str(e)}


def utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def library_versions():
    import numpy
    import sklearn
    out = {"python": platform.python_version(), "numpy": numpy.__version__,
           "sklearn": sklearn.__version__}
    try:
        import pandas
        out["pandas"] = pandas.__version__
    except ImportError:
        pass
    return out
