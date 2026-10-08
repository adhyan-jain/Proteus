"""Cache behaviour: memory guard, day-wise build == whole-corpus pipeline, provenance, loading.

Everything runs on tiny fixture CSVs written into tmp_path (unified CICFlowMeter header names taken
from data_full, random numbers, a few NaN/inf cells, duplicated rows). The real corpus is never read.
"""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import proteus.data_full as data_full
import proteus.intervention.cache as cache
from proteus.intervention.cache import (
    CACHE_VERSION, MemoryBlocker, build_cache, cache_status, group_fingerprint, hash_rows,
    load_cache, load_provenance, manifest_sha256s, provenance_path)

DAYS = {"Monday": ["BENIGN", "BENIGN", "FTP-Patator"], "Tuesday": ["BENIGN", "SSH-Patator"],
        "Wednesday": ["BENIGN", "DoS Hulk", "DoS slowloris"], "Thursday": ["BENIGN", "Web Attack"],
        "Friday": ["BENIGN", "DDoS", "PortScan", "Bot - Attempted"]}
FILES = [f"{d}-WorkingHours.csv" for d in DAYS]
IDENT = {"Flow ID", "Src IP", "Src Port", "Dst IP", "Timestamp"}


def _write_fixture(directory, n=70):
    cols = list(dict.fromkeys(data_full.INSDN_TO_CICIDS2017_COLS.values()))
    for d, (day, labels) in enumerate(DAYS.items()):
        rng = np.random.default_rng(d)
        frame = {}
        for c in cols:
            if c == "Flow ID":
                frame[c] = [f"flow-{day}-{i}" for i in range(n)]
            elif c in ("Src IP", "Dst IP"):
                frame[c] = [f"10.0.{d}.{i % 250}" for i in range(n)]
            elif c == "Timestamp":
                frame[c] = ["2017-07-03 08:00:00"] * n
            elif c == "Src Port":
                frame[c] = rng.integers(1, 65535, n)
            elif c == "Protocol":
                frame[c] = rng.choice([6, 17, 1], n)
            elif c == "Label":
                frame[c] = rng.choice(labels, n)
            else:
                frame[c] = np.round(rng.normal(size=n) * 10, 3)
        df = pd.DataFrame(frame)
        num = [c for c in cols if c not in IDENT | {"Protocol", "Label"}]
        df.loc[3, num[0]] = np.nan                       # dropped by cleaning
        df.loc[5, num[1]] = np.inf                       # dropped by cleaning
        df.iloc[10:15, 8:] = df.iloc[0:5, 8:].values     # duplicated feature vectors
        df.to_csv(directory / f"{day}-WorkingHours.csv", index=False)


def _manifest_md(directory, path):
    lines = ["| File | Size | Rows | SHA256 |", "|---|---|---|---|"]
    for f in FILES:
        sha = hashlib.sha256((directory / f).read_bytes()).hexdigest()
        lines.append(f"| {f} | 1 | 2 | {sha} |")
    path.write_text("\n".join(lines))
    return path


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    d = tmp_path_factory.mktemp("cicids_fixture")
    _write_fixture(d)
    return d


@pytest.fixture(scope="module")
def built(src, tmp_path_factory):
    out = tmp_path_factory.mktemp("cache_out") / "c.npz"
    md = _manifest_md(src, src.parent / "MANIFEST_fixture.md")
    build_cache(out, source_dir=src, files=FILES, manifest_md=md, min_available_gib=0.0)
    return out, md


def _reference(src, monkeypatch):
    """The pre-existing whole-corpus pipeline (what build_cache did before the day-wise rewrite)."""
    from sklearn.preprocessing import LabelEncoder
    monkeypatch.setattr(data_full, "CICIDS2017_DIR", src)
    df = data_full.clean_and_unify_cicids2017(data_full.load_cicids2017_raw())
    schema = data_full.get_feature_schema(df)
    df = pd.get_dummies(df, columns=["protocol"])
    cols = [c for c in df.columns if c not in ("label", "__source_day")
            and c not in schema["identifier_columns"]]
    le = LabelEncoder()
    return (df[cols].astype(np.float32).values, le.fit_transform(df["label"]).astype(np.int64),
            df["__source_day"].astype(str).values, [str(c) for c in le.classes_], cols)


def test_day_wise_build_is_bit_identical_to_the_whole_corpus_pipeline(built, src, monkeypatch):
    X, y, day, classes, cols = _reference(src, monkeypatch)
    b = load_cache(built[0], deep_verify=True)
    assert b.X.dtype == np.float32 and b.X.shape == X.shape
    assert np.array_equal(b.X, X) and np.array_equal(b.y, y)
    assert np.array_equal(b.day, day) and b.class_names == classes and b.feature_names == cols
    assert np.array_equal(b.group, hash_rows(X))                  # feature-hash grouping preserved
    assert set(b.day) == set(DAYS) and b.y.dtype == np.int64 and b.group.dtype == np.uint64
    assert len(b.X) < 5 * 70                                      # NaN / inf rows were dropped


def test_cache_loads_without_pickle(built):
    z = np.load(built[0], allow_pickle=False)                     # object arrays would raise here
    assert {"X", "y", "day", "group", "class_names", "feature_names", "version"} <= set(z.files)
    assert int(z["version"]) == CACHE_VERSION


def test_provenance_sidecar_records_sources_counts_and_fingerprint(built, src):
    path, md = built
    prov = load_provenance(path)
    assert provenance_path(path).exists() and prov["cache_version"] == CACHE_VERSION
    assert prov["source"]["verified_against_manifest"] is True
    expected = manifest_sha256s(md)
    for f in FILES:
        entry = prov["source"]["files"][f]
        assert entry["matches_manifest"] and entry["sha256"] == expected[f]
    b = load_cache(path)
    assert prov["group_hash"]["fingerprint_sha256"] == group_fingerprint(b.group) == \
        hashlib.sha256(np.ascontiguousarray(b.group).tobytes()).hexdigest()   # = data_fingerprint
    assert prov["n_rows"] == len(b.X) and prov["n_features"] == b.X.shape[1]
    assert sum(prov["rows_per_day"].values()) == len(b.X)
    for day, c in prov["cleaning_per_day"].items():
        assert c["rows_loaded"] == 70 and c["rows_kept"] < 70
    assert prov["build"]["peak_rss_gib"] > 0 and prov["build"]["forced_low_memory"] is False
    assert prov["git_sha"] is None or len(prov["git_sha"]) == 40
    assert "-0.0" in prov["group_hash"]["algorithm"] and prov["versions"]["numpy"]
    assert json.loads(provenance_path(path).read_text())          # strict, parseable


def test_source_hash_mismatch_stops_the_build(src, tmp_path):
    md = _manifest_md(src, tmp_path / "M.md")
    md.write_text(md.read_text().replace(hashlib.sha256((src / FILES[0]).read_bytes()).hexdigest(),
                                         "0" * 64))
    out = tmp_path / "bad.npz"
    with pytest.raises(RuntimeError, match="does not match data/MANIFEST.md"):
        build_cache(out, source_dir=src, files=FILES, manifest_md=md, min_available_gib=0.0)
    assert not out.exists() and not provenance_path(out).exists()


def test_memory_guard_blocks_before_anything_is_read(src, tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "available_memory_gib", lambda: 0.5)

    def boom(*a, **k):
        raise AssertionError("the guard must fire before any source is touched")
    monkeypatch.setattr(cache, "verify_sources", boom)
    monkeypatch.setattr(cache, "_build_arrays", boom)
    out = tmp_path / "blocked.npz"
    with pytest.raises(MemoryBlocker, match="0.50 GiB RAM available"):
        build_cache(out, source_dir=src, files=FILES)
    assert not out.exists()
    # the CLI reports the blocker and exits 2 without touching the real corpus
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cli.npz")
    assert cache.main(["build"]) == 2


def test_low_memory_bypass_is_explicit_and_recorded(src, tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "available_memory_gib", lambda: 0.5)
    out = tmp_path / "forced.npz"
    build_cache(out, source_dir=src, files=FILES, check_sources=False, force_low_memory=True)
    prov = load_provenance(out)
    assert prov["build"]["forced_low_memory"] is True
    assert prov["source"]["verified_against_manifest"] is False and prov["source"]["files"] is None


def test_default_memory_margin_covers_the_documented_estimate():
    assert cache.MIN_AVAILABLE_GIB >= 4.0
    rep = cache.memory_report()
    assert rep["mem_available_gib"] > 0 and rep["mem_total_gib"] >= rep["mem_available_gib"]
    assert {"swap_total_gib", "swap_used_gib"} <= set(rep)


def test_load_refuses_missing_tampered_or_unprovenanced_caches(built, tmp_path):
    path, _ = built
    with pytest.raises(FileNotFoundError, match="cache build"):
        load_cache(tmp_path / "nope.npz")

    # tampered group ids -> fingerprint mismatch
    z = dict(np.load(path, allow_pickle=False))
    z["group"] = z["group"][::-1].copy()
    bad = tmp_path / "tampered.npz"
    np.savez(bad, **z)
    provenance_path(bad).write_text(provenance_path(path).read_text())
    with pytest.raises(RuntimeError, match="group ids do not match"):
        load_cache(bad)

    # a cache without a sidecar never loads
    orphan = tmp_path / "orphan.npz"
    np.savez(orphan, **dict(np.load(path, allow_pickle=False)))
    with pytest.raises(FileNotFoundError, match="provenance"):
        load_cache(orphan)

    # wrong cache version
    z = dict(np.load(path, allow_pickle=False))
    z["version"] = np.array(CACHE_VERSION + 1)
    old = tmp_path / "old.npz"
    np.savez(old, **z)
    provenance_path(old).write_text(provenance_path(path).read_text())
    with pytest.raises(RuntimeError, match="cache version"):
        load_cache(old)


def test_status_reports_blocker_and_cache_presence(built, tmp_path, monkeypatch):
    missing = cache_status(tmp_path / "none.npz")
    assert missing["cache_exists"] is False and "build_memory_ok" in missing
    monkeypatch.setattr(cache, "memory_report", lambda: {
        "mem_total_gib": 15.0, "mem_available_gib": 3.2, "mem_free_gib": 0.4,
        "swap_total_gib": 22.0, "swap_used_gib": 11.0})
    assert cache_status(tmp_path / "none.npz")["build_memory_ok"] is False
    present = cache_status(built[0])
    assert present["cache_exists"] and present["provenance_exists"] and present["n_rows"] > 0


def test_atomic_publication_leaves_no_partial_files(built):
    leftovers = [p.name for p in built[0].parent.iterdir() if ".tmp" in p.name]
    assert leftovers == []
