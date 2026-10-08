"""api/research.py serves result files verbatim with provenance; missing stages are explicit."""
import hashlib
import json

import pytest
import api.research as research


class _Client:
    """Calls the endpoint functions directly (no httpx dependency in the shared venv)."""
    ROUTES = {"p0": research.p0, "p1": research.p1, "p1/decisions": research.p1_decisions,
              "verification": research.verification, "stages": research.stages,
              "artifacts": research.artifacts}

    def get(self, url):
        class R:
            def __init__(self, body):
                self._b = body

            def json(self):
                return self._b
        return R(self.ROUTES[url.replace("/api/research/", "")]())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "RESULTS", tmp_path)
    return _Client(), tmp_path


def test_missing_artifacts_are_explicitly_unavailable_never_filled(client):
    c, _ = client
    for path in ("p0", "p1", "p1/decisions", "verification"):
        body = c.get(f"/api/research/{path}").json()
        assert body["available"] is False and "not been run" in body["reason"]
    stages = c.get("/api/research/stages").json()["stages"]
    assert not stages["p1_summary"]["ran"] and stages["gates"]["p2_unlocked"] is None


def test_p1_is_returned_verbatim_with_hash_and_nonfinite_markers_become_null(client):
    c, tmp = client
    doc = {"kind": "p1_summary", "verdict": {"branch": "NEGATIVE", "p2_unlocked": False},
           "x": {"__nonfinite__": "nan"}, "ci": [1.5, {"__nonfinite__": "inf"}]}
    text = json.dumps(doc)
    (tmp / "intervention_p1_S1_B100_summary.json").write_text(text)
    body = c.get("/api/research/p1").json()
    assert body["available"] and body["doc"]["x"] is None and body["doc"]["ci"] == [1.5, None]
    assert body["doc"]["verdict"] == doc["verdict"]
    assert body["artifact"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert body["artifact"]["file"] == "results/intervention_p1_S1_B100_summary.json"
    st = c.get("/api/research/stages").json()["stages"]
    assert st["p1_summary"]["ran"] and st["gates"] == {"p2_unlocked": False, "p1_branch": "NEGATIVE"}


def test_p0_response_drops_the_heavy_cache_block_but_keeps_class_names(client):
    c, tmp = client
    doc = {"h1": {"outcome": "GO"}, "criteria": {"a": 1}, "params": {"b": 2},
           "data": {"n_rows": 5, "n_features": 2, "label_conflicts_diagnostic_only": {"n": 1},
                    "cache": {"class_names": ["A", "B"], "class_counts": {"A": 1}, "rows_per_day": {},
                              "huge": list(range(1000))}}}
    (tmp / "intervention_p0_S1_summary.json").write_text(json.dumps(doc))
    body = c.get("/api/research/p0").json()["doc"]
    assert body["data"]["class_names"] == ["A", "B"] and "huge" not in json.dumps(body)
    assert body["h1"]["outcome"] == "GO"


def test_artifact_registry_lists_every_known_file(client):
    c, tmp = client
    (tmp / "p1").mkdir()
    (tmp / "p1" / "intervention_p1_S1_B100_seed3.json").write_text("{}")
    body = c.get("/api/research/artifacts").json()
    assert {a["key"] for a in body["artifacts"]} >= {"p0_summary", "p1_summary", "p1_decisions", "verification"}
    assert all(not a["exists"] for a in body["artifacts"]) and body["p1_seed_files"] == [
        "intervention_p1_S1_B100_seed3.json"]
