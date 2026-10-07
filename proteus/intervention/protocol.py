"""Leak-free data partitioning and prequential replay (SPEC v1.0, sections 1.2, 1.3, 6).

Every partition is made on *groups* (rows with identical feature bytes share a group id), so a
duplicated flow can never sit on both sides of a boundary. The controller only ever receives a
`ControllerView`, which has no field for the reporting rows (E_t, S_report) or for future windows.

Known, documented limitation: groups can occur in both the pre-drift pool and the drift pool
(identical flows on different days). Those rows are not removed -- they are genuinely known
traffic -- but their number is recorded in `PartitionManifest.n_cross_pool_rows`.
"""
import proteus.config  # noqa: F401 -- must import before numpy to cap BLAS/OMP threads

import hashlib
import json
from dataclasses import dataclass, asdict, fields

import numpy as np

from proteus.intervention.cache import DataBundle

SPEC_VERSION = "1.1"

ROLE_FIT, ROLE_SEL, ROLE_GATE = 0, 1, 2
ROLE_NAMES = {ROLE_FIT: "fit", ROLE_SEL: "sel", ROLE_GATE: "gate"}
_ROLE_THRESHOLDS = (6, 8)  # group hash mod 10: [0,6) fit, [6,8) sel, [8,10) gate -> 0.6/0.2/0.2

_PRE_BUCKETS = ("train", "s_cal", "s_sel", "s_gate", "s_report", "pre_stream")


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    pre_days: tuple
    drift_days: tuple
    window_size: int = 3000
    n_pre_windows: int = 4
    n_post_windows: int = 10
    e_fraction: float = 0.3
    budget: int = 25
    s_size: int = 20000
    ref_size: int = 20000
    real_buffer_cap: int = 5000
    eval_buffer_cap: int = 5000


SCENARIOS = {
    "S1": ScenarioConfig("S1", ("Monday", "Tuesday", "Wednesday", "Thursday"), ("Friday",)),
    "S2": ScenarioConfig("S2", ("Monday", "Tuesday"), ("Wednesday",)),
}


@dataclass(frozen=True)
class WindowSpec:
    t: int
    phase: str            # "pre" or "post"
    e_idx: np.ndarray     # reporting rows, never learned from
    u_idx: np.ndarray     # unlabelled rows
    l_idx: np.ndarray     # labelled rows (budget B), arrive one window later
    l_role: np.ndarray    # ROLE_* per labelled row


@dataclass(frozen=True)
class PartitionManifest:
    seed: int
    config: ScenarioConfig
    data_fingerprint: str
    train_idx: np.ndarray
    ref_idx: np.ndarray
    s_cal_idx: np.ndarray
    s_sel_idx: np.ndarray
    s_gate_idx: np.ndarray
    s_report_idx: np.ndarray
    windows: tuple
    n_cross_pool_rows: int

    def digest(self):
        h = hashlib.sha256()
        h.update(SPEC_VERSION.encode())
        h.update(json.dumps(asdict(self.config), sort_keys=True).encode())
        h.update(str(self.seed).encode())
        h.update(self.data_fingerprint.encode())
        for name in ("train_idx", "ref_idx", "s_cal_idx", "s_sel_idx", "s_gate_idx",
                     "s_report_idx"):
            h.update(np.ascontiguousarray(getattr(self, name), dtype=np.int64).tobytes())
        for w in self.windows:
            h.update(f"{w.t}:{w.phase}".encode())
            for a in (w.e_idx, w.u_idx, w.l_idx, w.l_role):
                h.update(np.ascontiguousarray(a, dtype=np.int64).tobytes())
        return h.hexdigest()

    def sizes(self):
        return {
            "train": len(self.train_idx), "ref": len(self.ref_idx),
            "s_cal": len(self.s_cal_idx), "s_sel": len(self.s_sel_idx),
            "s_gate": len(self.s_gate_idx), "s_report": len(self.s_report_idx),
            "n_windows": len(self.windows), "n_cross_pool_rows": self.n_cross_pool_rows,
        }


def _ro(a):
    a = np.asarray(a)
    a.setflags(write=False)
    return a


def _assign_groups(group_ids, labels, probs, rng):
    """Group-level, class-stratified random bucket assignment.

    Every row of a group gets the same bucket. Within each class (the label of the group's first
    row), groups are shuffled and dealt to buckets with largest-remainder rounding of `probs`,
    so bucket sizes track `probs` per class (by group count; sizes in rows are approximate when
    some groups are large)."""
    probs = np.asarray(probs, dtype=float)
    probs = probs / probs.sum()
    ug, inv = np.unique(group_ids, return_inverse=True)
    first_label = np.empty(len(ug), dtype=labels.dtype)
    first_label[inv[::-1]] = labels[::-1]  # later writes win, so reversing keeps the first row
    bucket_of_group = np.empty(len(ug), dtype=np.int64)
    for c in np.unique(first_label):
        gi = np.flatnonzero(first_label == c)
        gi = gi[rng.permutation(len(gi))]
        exact = probs * len(gi)
        counts = np.floor(exact).astype(np.int64)
        rem = int(len(gi) - counts.sum())
        if rem > 0:
            frac = exact - counts
            extra = rng.choice(len(probs), size=rem, replace=False, p=frac / frac.sum())
            counts[extra] += 1
        bucket_of_group[gi] = np.repeat(np.arange(len(probs)), counts)
    return bucket_of_group[inv]


def _role_of_groups(group, seed):
    salt = np.uint64((int(seed) * 0x9E3779B97F4A7C15) % (1 << 64))
    r = ((np.asarray(group, dtype=np.uint64) ^ salt) >> np.uint64(13)) % np.uint64(10)
    role = np.full(len(r), ROLE_GATE, dtype=np.int64)
    role[r < _ROLE_THRESHOLDS[1]] = ROLE_SEL
    role[r < _ROLE_THRESHOLDS[0]] = ROLE_FIT
    return role


def _build_windows(data, pool_idx, cfg, n_windows, phase, t0, seed, rng):
    """Cut `pool_idx` into non-replacing windows. Groups are first assigned to the reporting
    side (E) or the learning side, so no group is shared between E_t and any L_t / U_t."""
    if n_windows == 0:
        return []
    side = _assign_groups(data.group[pool_idx], data.y[pool_idx],
                          [cfg.e_fraction, 1.0 - cfg.e_fraction], rng)
    e_rows = pool_idx[side == 0]
    ne_rows = pool_idx[side == 1]
    e_rows = e_rows[rng.permutation(len(e_rows))]
    ne_rows = ne_rows[rng.permutation(len(ne_rows))]
    e_per = int(round(cfg.window_size * cfg.e_fraction))
    ne_per = cfg.window_size - e_per
    if cfg.budget > ne_per:
        raise ValueError(f"label budget {cfg.budget} exceeds learning rows per window {ne_per}")
    if len(e_rows) < n_windows * e_per or len(ne_rows) < n_windows * ne_per:
        raise ValueError(
            f"{phase} pool too small for {n_windows} windows of {cfg.window_size}: have "
            f"{len(e_rows)} E rows (need {n_windows * e_per}) and {len(ne_rows)} learning rows "
            f"(need {n_windows * ne_per})")
    out = []
    for k in range(n_windows):
        e = e_rows[k * e_per:(k + 1) * e_per]
        ne = ne_rows[k * ne_per:(k + 1) * ne_per]
        l_idx, u_idx = ne[:cfg.budget], ne[cfg.budget:]
        out.append(WindowSpec(t=t0 + k, phase=phase, e_idx=_ro(e), u_idx=_ro(u_idx),
                              l_idx=_ro(l_idx),
                              l_role=_ro(_role_of_groups(data.group[l_idx], seed))))
    return out


def build_partitions(data: DataBundle, cfg: ScenarioConfig, seed: int) -> PartitionManifest:
    overlap = set(cfg.pre_days) & set(cfg.drift_days)
    if overlap:
        raise ValueError(f"pre_days and drift_days overlap: {sorted(overlap)}")
    pre_idx = np.flatnonzero(np.isin(data.day, cfg.pre_days))
    drift_idx = np.flatnonzero(np.isin(data.day, cfg.drift_days))
    if len(pre_idx) == 0 or len(drift_idx) == 0:
        raise ValueError(f"scenario {cfg.name}: empty pre ({len(pre_idx)}) or drift "
                         f"({len(drift_idx)}) pool")

    n_pre = len(pre_idx)
    s_p = min(cfg.s_size / n_pre, 0.05)
    stream_p = min(1.5 * cfg.n_pre_windows * cfg.window_size / n_pre, 0.5)
    probs = [1.0 - 4 * s_p - stream_p, s_p, s_p, s_p, s_p, stream_p]
    rng_pre = np.random.default_rng([seed, 0])
    bucket = _assign_groups(data.group[pre_idx], data.y[pre_idx], probs, rng_pre)
    parts = {name: pre_idx[bucket == i] for i, name in enumerate(_PRE_BUCKETS)}

    windows = _build_windows(data, parts["pre_stream"], cfg, cfg.n_pre_windows, "pre", 0, seed,
                             np.random.default_rng([seed, 1]))
    windows += _build_windows(data, drift_idx, cfg, cfg.n_post_windows, "post",
                              cfg.n_pre_windows, seed, np.random.default_rng([seed, 2]))

    train = parts["train"]
    ref_rng = np.random.default_rng([seed, 3])
    ref = np.sort(ref_rng.choice(train, size=min(cfg.ref_size, len(train)), replace=False))

    n_cross = int(np.isin(data.group[drift_idx], data.group[pre_idx]).sum())
    return PartitionManifest(
        seed=seed, config=cfg,
        data_fingerprint=hashlib.sha256(np.ascontiguousarray(data.group).tobytes()).hexdigest(),
        train_idx=_ro(train), ref_idx=_ro(ref), s_cal_idx=_ro(parts["s_cal"]),
        s_sel_idx=_ro(parts["s_sel"]), s_gate_idx=_ro(parts["s_gate"]),
        s_report_idx=_ro(parts["s_report"]), windows=tuple(windows), n_cross_pool_rows=n_cross)


@dataclass(frozen=True)
class StreamStep:
    t: int
    phase: str
    spec: WindowSpec
    arrived_idx: np.ndarray   # labels of window t-1 (label delay = 1); empty at t=0
    arrived_role: np.ndarray


class StreamReplay:
    """Yields windows in order, with the previous window's labels attached (never the current
    window's)."""

    def __init__(self, manifest: PartitionManifest):
        self.manifest = manifest

    def __iter__(self):
        prev = None
        empty = np.empty(0, dtype=np.int64)
        for spec in self.manifest.windows:
            yield StreamStep(
                t=spec.t, phase=spec.phase, spec=spec,
                arrived_idx=prev.l_idx if prev is not None else empty,
                arrived_role=prev.l_role if prev is not None else empty)
            prev = spec


@dataclass(frozen=True)
class ControllerView:
    """The ONLY object a controller receives. By construction it has no field that can reach the
    reporting rows (E_t, S_report), the KS reference (S_cal), unlabelled rows or future windows."""
    ref_X: np.ndarray
    ref_y: np.ndarray
    real_X: np.ndarray       # D_real: real fit rows, FIFO
    real_y: np.ndarray
    sel_X: np.ndarray        # D_sel: drift labels used for step decisions
    sel_y: np.ndarray
    gate_X: np.ndarray       # D_gate: drift labels used only for promotion
    gate_y: np.ndarray
    s_sel_X: np.ndarray      # stable-traffic set for step decisions
    s_sel_y: np.ndarray
    s_gate_X: np.ndarray     # stable-traffic set for promotion
    s_gate_y: np.ndarray
    class_names: tuple

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, np.ndarray):
                v.setflags(write=False)


class StreamState:
    """Accumulates arrived labels into the fit / sel / gate buffers and builds ControllerViews."""

    def __init__(self, data: DataBundle, manifest: PartitionManifest):
        self.data = data
        self.manifest = manifest
        self._real = np.empty(0, dtype=np.int64)
        self._sel = np.empty(0, dtype=np.int64)
        self._gate = np.empty(0, dtype=np.int64)
        self._last_t = -1

    def ingest(self, step: StreamStep):
        """Add the labels that arrived at `step`. They must come from an earlier window."""
        cfg = self.manifest.config
        if step.t <= self._last_t:
            raise ValueError(f"steps must be ingested in order (got t={step.t} after "
                             f"{self._last_t})")
        if np.intersect1d(step.arrived_idx, step.spec.l_idx).size:
            raise AssertionError("label delay violated: current window labels arrived early")
        self._last_t = step.t
        idx, role = step.arrived_idx, step.arrived_role
        self._real = np.concatenate([self._real, idx[role == ROLE_FIT]])[-cfg.real_buffer_cap:]
        self._sel = np.concatenate([self._sel, idx[role == ROLE_SEL]])[-cfg.eval_buffer_cap:]
        self._gate = np.concatenate([self._gate, idx[role == ROLE_GATE]])[-cfg.eval_buffer_cap:]

    def provenance(self):
        """Global row indices behind every array of the current view (for audits and tests)."""
        m = self.manifest
        return {"ref": m.ref_idx, "real": self._real, "sel": self._sel, "gate": self._gate,
                "s_sel": m.s_sel_idx, "s_gate": m.s_gate_idx}

    def view(self) -> ControllerView:
        p = self.provenance()
        X, y = self.data.X, self.data.y
        return ControllerView(
            ref_X=X[p["ref"]], ref_y=y[p["ref"]],
            real_X=X[p["real"]], real_y=y[p["real"]],
            sel_X=X[p["sel"]], sel_y=y[p["sel"]],
            gate_X=X[p["gate"]], gate_y=y[p["gate"]],
            s_sel_X=X[p["s_sel"]], s_sel_y=y[p["s_sel"]],
            s_gate_X=X[p["s_gate"]], s_gate_y=y[p["s_gate"]],
            class_names=tuple(self.data.class_names))
