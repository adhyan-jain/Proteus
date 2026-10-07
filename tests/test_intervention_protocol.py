"""Leakage and protocol tests for proteus.intervention (SPEC v1.0, sections 1.2, 1.3, 6).

Synthetic data only. The data deliberately contains many exact-duplicate rows (within and across
days) so that group-disjointness is a non-trivial property, not an accident of unique rows.
"""
import numpy as np
import pytest

from proteus.intervention.cache import DataBundle, hash_rows
from proteus.intervention.protocol import (
    ROLE_FIT, ROLE_GATE, ROLE_SEL, ControllerView, PartitionManifest, ScenarioConfig,
    StreamReplay, StreamState, StreamStep, _assign_groups, build_partitions)

CFG = ScenarioConfig("T", ("Monday", "Tuesday", "Wednesday", "Thursday"), ("Friday",),
                     window_size=300, n_pre_windows=2, n_post_windows=4, budget=20,
                     s_size=400, ref_size=500, real_buffer_cap=200, eval_buffer_cap=200)

N_PER_DAY = 20000
N_CROSS_PLANTED = 50


def _make_data(seed=0):
    rng = np.random.default_rng(seed)
    days, ys, Xs = [], [], []
    for d, day in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]):
        classes = [0, 1, 2, 3] if day != "Friday" else [0, 4, 5]
        y = rng.choice(classes, size=N_PER_DAY, p=[0.7] + [0.3 / (len(classes) - 1)] *
                       (len(classes) - 1))
        X = rng.normal(size=(N_PER_DAY, 6)).astype(np.float32) + y[:, None].astype(np.float32)
        dup_src = rng.integers(0, N_PER_DAY, size=N_PER_DAY // 3)
        dup_dst = rng.integers(0, N_PER_DAY, size=N_PER_DAY // 3)
        X[dup_dst] = X[dup_src]
        y[dup_dst] = y[dup_src]
        days += [day] * N_PER_DAY
        ys.append(y)
        Xs.append(X)
    X = np.vstack(Xs)
    y = np.concatenate(ys).astype(np.int64)
    fri = np.flatnonzero(np.array(days) == "Friday")
    mon = np.flatnonzero(np.array(days) == "Monday")
    planted = rng.choice(len(fri), size=N_CROSS_PLANTED, replace=False)
    X[fri[planted]] = X[mon[:N_CROSS_PLANTED]]
    y[fri[planted]] = y[mon[:N_CROSS_PLANTED]]
    return DataBundle(X=X, y=y, day=np.array(days), group=hash_rows(X),
                      class_names=[f"c{i}" for i in range(6)],
                      feature_names=[f"f{i}" for i in range(6)])


@pytest.fixture(scope="module")
def data():
    return _make_data()


@pytest.fixture(scope="module")
def manifest(data):
    return build_partitions(data, CFG, seed=7)


def _groups(data, *idx_arrays):
    idx = np.concatenate([np.asarray(a, dtype=np.int64) for a in idx_arrays])
    return set(data.group[idx].tolist())


def _concat(windows, attr):
    arrs = [getattr(w, attr) for w in windows]
    return np.concatenate(arrs) if arrs else np.empty(0, dtype=np.int64)


def test_hash_rows_is_stable_and_canonicalises_negative_zero():
    a = np.array([[0.0, 1.0], [-0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    h = hash_rows(a)
    assert h[0] == h[1]
    assert h[0] != h[2]
    assert np.array_equal(h, hash_rows(a.copy()))


def test_databundle_rejects_length_mismatch():
    with pytest.raises(ValueError):
        DataBundle(X=np.zeros((3, 2), np.float32), y=np.zeros(2, np.int64),
                   day=np.array(["a"] * 3), group=np.zeros(3, np.uint64),
                   class_names=[], feature_names=[])


def test_assign_groups_keeps_groups_whole_and_is_stratified():
    rng = np.random.default_rng(0)
    group = np.repeat(np.arange(2000, dtype=np.uint64), 3)
    labels = np.repeat((np.arange(2000) % 4).astype(np.int64), 3)
    bucket = _assign_groups(group, labels, [0.5, 0.3, 0.2], rng)
    for g in (0, 17, 1999):
        assert len(set(bucket[group == g])) == 1
    for c in range(4):
        frac = np.mean(bucket[labels == c] == 0)
        assert abs(frac - 0.5) < 0.02


def test_pre_pool_partitions_are_group_disjoint(data, manifest):
    pre = [w for w in manifest.windows if w.phase == "pre"]
    sets = {
        "train": _groups(data, manifest.train_idx),
        "s_cal": _groups(data, manifest.s_cal_idx),
        "s_sel": _groups(data, manifest.s_sel_idx),
        "s_gate": _groups(data, manifest.s_gate_idx),
        "s_report": _groups(data, manifest.s_report_idx),
        "pre_stream": _groups(data, _concat(pre, "e_idx"), _concat(pre, "u_idx"),
                              _concat(pre, "l_idx")),
    }
    names = list(sets)
    for i, a in enumerate(names):
        assert sets[a], f"{a} is empty"
        for b in names[i + 1:]:
            assert not (sets[a] & sets[b]), f"groups shared between {a} and {b}"


def test_reporting_rows_are_group_disjoint_from_all_learning_rows(data, manifest):
    for phase in ("pre", "post"):
        ws = [w for w in manifest.windows if w.phase == phase]
        e = _groups(data, _concat(ws, "e_idx"))
        learn = _groups(data, _concat(ws, "u_idx"), _concat(ws, "l_idx"))
        assert e and learn
        assert not (e & learn), f"{phase}: E_t shares a group with U/L rows"


def test_windows_are_non_replacing_and_correctly_sized(manifest):
    all_idx = np.concatenate([np.concatenate([w.e_idx, w.u_idx, w.l_idx])
                              for w in manifest.windows])
    assert len(np.unique(all_idx)) == len(all_idx)
    assert len(manifest.windows) == CFG.n_pre_windows + CFG.n_post_windows
    for w in manifest.windows:
        assert len(w.e_idx) + len(w.u_idx) + len(w.l_idx) == CFG.window_size
        assert len(w.e_idx) == round(CFG.window_size * CFG.e_fraction)
        assert len(w.l_idx) == CFG.budget
        assert len(w.l_role) == CFG.budget


def test_days_are_respected(data, manifest):
    pre_days = set(CFG.pre_days)
    for w in manifest.windows:
        for a in (w.e_idx, w.u_idx, w.l_idx):
            days = set(data.day[a].tolist())
            assert days <= (pre_days if w.phase == "pre" else set(CFG.drift_days))
    for a in (manifest.train_idx, manifest.s_cal_idx, manifest.s_sel_idx, manifest.s_gate_idx,
              manifest.s_report_idx, manifest.ref_idx):
        assert set(data.day[a].tolist()) <= pre_days


def test_label_roles_are_a_function_of_the_group(data, manifest):
    role_of = {}
    for w in manifest.windows:
        for g, r in zip(data.group[w.l_idx].tolist(), w.l_role.tolist()):
            assert role_of.setdefault(g, r) == r, "a group changed role"
    assert set(role_of.values()) <= {ROLE_FIT, ROLE_SEL, ROLE_GATE}


def test_label_roles_split_roughly_60_20_20(data):
    big = build_partitions(data, ScenarioConfig(
        "T2", CFG.pre_days, CFG.drift_days, window_size=2000, n_pre_windows=1,
        n_post_windows=4, budget=1000, s_size=400, ref_size=500), seed=1)
    roles = np.concatenate([w.l_role for w in big.windows])
    frac = np.bincount(roles, minlength=3) / len(roles)
    assert abs(frac[ROLE_FIT] - 0.6) < 0.06
    assert abs(frac[ROLE_SEL] - 0.2) < 0.06
    assert abs(frac[ROLE_GATE] - 0.2) < 0.06


def test_label_delay_is_exactly_one_window(manifest):
    steps = list(StreamReplay(manifest))
    assert len(steps) == len(manifest.windows)
    assert len(steps[0].arrived_idx) == 0
    for k in range(1, len(steps)):
        assert np.array_equal(steps[k].arrived_idx, manifest.windows[k - 1].l_idx)
        assert not np.intersect1d(steps[k].arrived_idx, steps[k].spec.l_idx).size


def test_stream_state_rejects_early_labels_and_out_of_order_steps(data, manifest):
    state = StreamState(data, manifest)
    steps = list(StreamReplay(manifest))
    cheat = StreamStep(t=steps[1].t, phase=steps[1].phase, spec=steps[1].spec,
                       arrived_idx=steps[1].spec.l_idx, arrived_role=steps[1].spec.l_role)
    with pytest.raises(AssertionError):
        state.ingest(cheat)
    state.ingest(steps[0])
    state.ingest(steps[1])
    with pytest.raises(ValueError):
        state.ingest(steps[1])


def test_controller_view_exposes_only_allowed_fields():
    assert set(ControllerView.__dataclass_fields__) == {
        "ref_X", "ref_y", "real_X", "real_y", "sel_X", "sel_y", "gate_X", "gate_y",
        "s_sel_X", "s_sel_y", "s_gate_X", "s_gate_y", "class_names"}


def test_view_never_contains_reporting_or_future_rows(data, manifest):
    state = StreamState(data, manifest)
    e_groups = _groups(data, _concat(manifest.windows, "e_idx"))
    report_groups = _groups(data, manifest.s_report_idx)
    cal_groups = _groups(data, manifest.s_cal_idx)
    for step in StreamReplay(manifest):
        state.ingest(step)
        prov = state.provenance()
        past_l = _concat([w for w in manifest.windows if w.t < step.t], "l_idx")
        allowed_drift_rows = set(past_l.tolist())
        for name in ("real", "sel", "gate"):
            rows = set(prov[name].tolist())
            assert rows <= allowed_drift_rows, f"{name} holds rows from t >= {step.t}"
        all_groups = _groups(data, *prov.values())
        assert not (all_groups & e_groups), "view reaches an E_t group"
        assert not (all_groups & report_groups), "view reaches an S_report group"
        assert not (all_groups & cal_groups), "view reaches an S_cal group"
        # fit / sel / gate buffers never share a group
        g_real, g_sel, g_gate = (_groups(data, prov[n]) if len(prov[n]) else set()
                                 for n in ("real", "sel", "gate"))
        assert not (g_real & g_sel) and not (g_real & g_gate) and not (g_sel & g_gate)


def test_view_arrays_are_read_only_and_buffers_are_capped(data, manifest):
    state = StreamState(data, manifest)
    for step in StreamReplay(manifest):
        state.ingest(step)
    view = state.view()
    with pytest.raises(ValueError):
        view.ref_X[0, 0] = 1.0
    with pytest.raises(ValueError):
        view.real_y[:1] = 0
    assert len(view.real_X) <= CFG.real_buffer_cap
    assert len(view.sel_X) <= CFG.eval_buffer_cap
    assert len(view.ref_X) == min(CFG.ref_size, len(manifest.train_idx))


def test_ref_reservoir_comes_from_train_only(manifest):
    assert set(manifest.ref_idx.tolist()) <= set(manifest.train_idx.tolist())


def test_manifest_is_reproducible_from_the_seed(data, manifest):
    again = build_partitions(data, CFG, seed=7)
    assert again.digest() == manifest.digest()
    assert build_partitions(data, CFG, seed=8).digest() != manifest.digest()


def test_cross_pool_duplicates_are_counted_not_hidden(manifest):
    assert manifest.n_cross_pool_rows >= N_CROSS_PLANTED


def test_invalid_configs_fail_loudly(data):
    with pytest.raises(ValueError):
        build_partitions(data, ScenarioConfig("bad", ("Monday",), ("Monday",)), seed=0)
    with pytest.raises(ValueError):
        build_partitions(data, ScenarioConfig("bad", CFG.pre_days, CFG.drift_days,
                                              window_size=300, budget=500), seed=0)
    with pytest.raises(ValueError):
        build_partitions(data, ScenarioConfig("bad", CFG.pre_days, CFG.drift_days,
                                              window_size=300, n_post_windows=10_000), seed=0)


def test_manifest_type_is_exported(manifest):
    assert isinstance(manifest, PartitionManifest)
    assert manifest.sizes()["n_windows"] == CFG.n_pre_windows + CFG.n_post_windows
