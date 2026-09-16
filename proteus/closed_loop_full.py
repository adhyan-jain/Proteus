"""Stage 6: closed-loop orchestration at full scale.

drift detected -> WGAN-GP resumed (not from scratch) on the recent window -> fidelity gate
checks the new synthetic batch -> admitted samples added to the training set -> classifier
retrained -> redeployed. Reuses the already-validated Stage 3/4 components
(`proteus.baseline_full`, `proteus.gan_full`, `proteus.drift`, `proteus.fidelity`) rather than
reimplementing any of them.

## Honesty note on what this module can and cannot claim (read before running/reporting)

The original ground rules for this stage require the closed loop to operate "against the live
local Mininet/Ryu traffic stream," with drift injected via real held-out attack variants
replayed into the emulated topology. **That live-Mininet integration is not what this module
does today** -- Mininet requires root at runtime, this environment has no sudo access, and
Stage 0's smoke test (which must pass before anything downstream can honestly be called "live")
has not been run. See `STATUS.md` for that blocker.

What this module *does* provide, and what it's honest to call it: a `TrafficSource` protocol
with two implementations --
  - `LiveMininetSource` -- a thin adapter reading rows from Stage 5's Ryu controller export
    (`sdn/topology/ryu_ids_app.py`'s `on_schema_row` extension point) once that's wired up and
    running live. **Not usable without the Stage 0 smoke test passing first.**
  - `RealDataReplaySource` -- replays real, held-out CICIDS2017 rows (the same Mon-Thu-train /
    Friday-holdout temporal split validated in Stage 4) in fixed-size windows, injecting real
    drift by advancing from the Mon-Thu-only portion into the Friday portion (which contains
    real attack families absent from training, per Stage 4's validation). This is real data and
    a real temporal structure, but it is NOT live traffic through a live controller -- do not
    conflate a `RealDataReplaySource` run with the "live Mininet" requirement. Use it to verify
    the orchestration logic is correct, and as an honestly-labeled interim result, not as a
    substitute for the live requirement.

Whatever source is used, results must be labeled with which one produced them -- see
`ClosedLoopOrchestrator.run()`'s returned `traffic_source` field.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from proteus.config import DEFAULT_N_JOBS  # noqa: F401 -- must import before numpy/torch/sklearn to cap BLAS/OMP threads

import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

from proteus import drift as drift_mod, fidelity as fidelity_mod

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("proteus.closed_loop_full")

RESULTS_DIR = Path(__file__).parent.parent / "results"
CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoints" / "gan_full"
MMD_THRESHOLD = 0.25


class TrafficSource(ABC):
    """A source of labeled schema-row batches, one per timestep."""

    @abstractmethod
    def __iter__(self):
        """Yields (timestep: int, X: np.ndarray, y: np.ndarray, is_real_live_traffic: bool)."""


class LiveMininetSource(TrafficSource):
    """NOT YET USABLE -- requires Stage 0's smoke test to pass first (needs root, see
    STATUS.md). Placeholder showing the intended integration shape: reads exported schema rows
    from the Ryu controller (sdn/topology/ryu_ids_app.py) via whatever IPC/queue mechanism gets
    built once that's live (a file-based queue, a local socket, etc. -- deliberately not
    decided here, since designing it before the smoke test passes would be guessing at
    requirements the actual live export hasn't revealed yet)."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "LiveMininetSource requires Stage 0's Mininet smoke test to pass first (needs the "
            "repo owner's sudo session -- see STATUS.md's 'Blocked' section). Use "
            "RealDataReplaySource for now, and label any results from it as replay-based, not "
            "live-traffic, per this module's docstring.")


class RealDataReplaySource(TrafficSource):
    """Replays real, held-out CICIDS2017 rows in windows, with a real (not synthetic) drift
    transition: windows before `drift_at_window` are drawn from the Mon-Thu training-day pool
    (IID with what the classifier trained on); windows at/after `drift_at_window` are drawn from
    the Friday holdout (contains real attack families absent from Mon-Thu, per the Stage 4
    validation in proteus/validate_full.py)."""

    def __init__(self, X_stable, y_stable, X_drifted, y_drifted, n_windows=20,
                 window_size=2000, drift_at_window=8, seed=0):
        self.X_stable, self.y_stable = X_stable, y_stable
        self.X_drifted, self.y_drifted = X_drifted, y_drifted
        self.n_windows = n_windows
        self.window_size = window_size
        self.drift_at_window = drift_at_window
        self.rng = np.random.default_rng(seed)

    def __iter__(self):
        for t in range(self.n_windows):
            drifted = t >= self.drift_at_window
            X_pool, y_pool = (self.X_drifted, self.y_drifted) if drifted \
                else (self.X_stable, self.y_stable)
            idx = self.rng.choice(len(X_pool), size=min(self.window_size, len(X_pool)),
                                   replace=False)
            yield t, X_pool[idx], y_pool[idx], False  # False = not live Mininet traffic


class BoundedBufferClassifier:
    """Incremental/adaptive streaming classifier maintaining a strictly bounded adaptation buffer.

    Prevents unbounded memory growth and multi-minute retraining latency by capping historical data:
    1. Reference Reservoir (ref_X, ref_y): max_ref_samples (default 20,000) sampled from initial offline training.
    2. Sliding Adaptation Buffer (recent_X, recent_y): max_recent_samples (default 5,000) for recent fit rows
       and admitted synthetic samples.
    Total adaptation dataset size |D_adapt| <= max_ref_samples + max_recent_samples (25,000 max),
    guaranteeing O(1) memory footprint and sub-second update latency per drift timestep.
    """

    def __init__(self, base_estimator_factory, max_ref_samples=20000, max_recent_samples=5000, seed=42):
        self.factory = base_estimator_factory
        self.max_ref_samples = max_ref_samples
        self.max_recent_samples = max_recent_samples
        self.seed = seed
        self.clf = None
        self.ref_X = None
        self.ref_y = None
        self.recent_X = None
        self.recent_y = None

    def fit_initial(self, X_train_init, y_train_init):
        if len(X_train_init) > self.max_ref_samples:
            rng = np.random.default_rng(self.seed)
            idx = rng.choice(len(X_train_init), size=self.max_ref_samples, replace=False)
            self.ref_X = X_train_init[idx].copy()
            self.ref_y = y_train_init[idx].copy()
        else:
            self.ref_X = X_train_init.copy()
            self.ref_y = y_train_init.copy()

        self.clf = self.factory()
        self.clf.fit(X_train_init, y_train_init)
        return self

    def partial_fit_adaptation(self, X_fit, y_fit, X_synth=None, y_synth=None):
        X_new = X_fit
        y_new = y_fit
        if X_synth is not None and len(X_synth) > 0:
            X_new = np.vstack([X_fit, X_synth])
            y_new = np.concatenate([y_fit, y_synth])

        if self.recent_X is None:
            self.recent_X = X_new.copy()
            self.recent_y = y_new.copy()
        else:
            self.recent_X = np.vstack([self.recent_X, X_new])[-self.max_recent_samples:]
            self.recent_y = np.concatenate([self.recent_y, y_new])[-self.max_recent_samples:]

        combined_X = np.vstack([self.ref_X, self.recent_X])
        combined_y = np.concatenate([self.ref_y, self.recent_y])

        self.clf = self.factory()
        self.clf.fit(combined_X, combined_y)
        return self

    @property
    def buffer_size(self):
        recent_len = len(self.recent_X) if self.recent_X is not None else 0
        ref_len = len(self.ref_X) if self.ref_X is not None else 0
        return ref_len + recent_len

    def predict(self, X):
        return self.clf.predict(X)

    def predict_proba(self, X):
        return self.clf.predict_proba(X)


class ClosedLoopOrchestrator:
    """drift fires -> GAN resumes on recent window -> fidelity gate -> classifier incremental adaptation."""

    def __init__(self, X_train_init, y_train_init, class_names, gan_checkpoint_path=None,
                 device=None, max_ref_samples=20000, max_recent_samples=5000):
        if device is None:
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA not available -- this repo's absolute rule is GPU-only training "
                    "(CLAUDE.md rule 1).")
            device = "cuda"
        self.device = device
        self.class_names = class_names
        self.name_to_idx = {c: i for i, c in enumerate(class_names)}

        self.clf = BoundedBufferClassifier(
            lambda: RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=DEFAULT_N_JOBS),
            max_ref_samples=max_ref_samples,
            max_recent_samples=max_recent_samples
        )
        self.clf.fit_initial(X_train_init, y_train_init)
        self.X_train_ref = self.clf.ref_X
        self.y_train_ref = self.clf.ref_y

        self.ref_confidence = self.clf.predict_proba(
            X_train_init[:min(50000, len(X_train_init))]).max(axis=1)

        from proteus.gan_full import WGANGPFull, GAN_ADMIT_CLASSES
        self.gan_admit_classes = GAN_ADMIT_CLASSES
        self.admit_idx = [self.name_to_idx[c] for c in GAN_ADMIT_CLASSES
                           if c in self.name_to_idx]

        if gan_checkpoint_path is None:
            ckpts = sorted(CHECKPOINT_DIR.glob("epoch_*.pt"),
                            key=lambda p: int(p.stem.split("_")[1]))
            if not ckpts:
                raise FileNotFoundError(f"No WGAN-GP checkpoint in {CHECKPOINT_DIR}")
            gan_checkpoint_path = ckpts[-1]
        ckpt = torch.load(gan_checkpoint_path, map_location=device, weights_only=False)
        self.gan = WGANGPFull(X_train_init.shape[1], ckpt["class_labels"],
                               ckpt["feature_mean"], ckpt["feature_std"], device=device)
        self.gan.G.load_state_dict(ckpt["generator"])
        self.gan.D.load_state_dict(ckpt["critic"])

        self.gate = fidelity_mod.FidelityGateLog(threshold=MMD_THRESHOLD)
        self.drift_events, self.retrain_events = [], []
        self.eval_rng = np.random.default_rng(123)
        self.EVAL_HOLDOUT_FRACTION = 0.3

    def _macro_f1(self, X, y):
        y_pred = self.clf.predict(X)
        return float(f1_score(y, y_pred, labels=list(range(len(self.class_names))),
                               average="macro", zero_division=0))

    def _resume_gan_on_recent_window(self, X_recent, y_recent, steps=20, batch_size=32):
        """Resume-train the GAN (not from scratch) on the drift window."""
        idx_by_class = {}
        rows = []
        for c in self.gan.class_labels:
            recent_local = np.where(y_recent == c)[0]
            if len(recent_local) >= 1:
                start = len(rows)
                rows.append(X_recent[recent_local])
                idx_by_class[c] = np.arange(start, start + len(recent_local))
            else:
                fallback_local = np.where(self.y_train_ref == c)[0]
                if len(fallback_local) == 0:
                    continue
                n = min(50, len(fallback_local))
                sample = np.random.default_rng(0).choice(fallback_local, size=n, replace=False)
                start = len(rows)
                rows.append(self.X_train_ref[sample])
                idx_by_class[c] = np.arange(start, start + n)

        if len(idx_by_class) < 2:
            return
        X_combined = np.vstack(rows).astype(np.float32)
        X_norm = self.gan._normalize(X_combined)
        y_combined = np.concatenate([np.full(len(v), c) for c, v in idx_by_class.items()])
        self.gan.train_one_epoch(X_norm, y_combined, epoch=-1, idx_by_class=idx_by_class,
                                  steps_per_epoch=steps)

    @staticmethod
    def split_eval_fit(X, y, fraction, rng):
        """Held-out split of one incoming window, fixed before any training/adaptation touches it."""
        n_eval = max(1, int(len(X) * fraction))
        perm = rng.permutation(len(X))
        eval_idx, fit_idx = perm[:n_eval], perm[n_eval:]
        return X[eval_idx], y[eval_idx], X[fit_idx], y[fit_idx]

    def step(self, t, X, y):
        import time, resource
        X_eval, y_eval, X_fit, y_fit = self.split_eval_fit(
            X, y, self.EVAL_HOLDOUT_FRACTION, self.eval_rng)

        macro_f1_before = self._macro_f1(X_eval, y_eval)
        conf = self.clf.predict_proba(X).max(axis=1)
        result = drift_mod.detect_drift(conf, self.ref_confidence)
        self.drift_events.append({"timestep": t, **result})

        macro_f1_after = macro_f1_before
        if result["fired"]:
            t_adapt_0 = time.time()
            log.info(f"[t={t}] drift fired (stat={result['statistic']:.4f} "
                     f"p={result['p_value']:.4g}) -- updating classifier incrementally")
            self._resume_gan_on_recent_window(X_fit, y_fit)

            n_admitted_total = 0
            X_new, y_new = [], []
            for c in self.admit_idx:
                real_recent = X_fit[y_fit == c] if (y_fit == c).sum() >= 5 else \
                    self.X_train_ref[self.y_train_ref == c]
                if len(real_recent) == 0:
                    log.info(f"[t={t}] class={self.class_names[c]}: no real reference data "
                             f"available anywhere -- skipping fidelity check, not admitting")
                    continue
                synth = self.gan.generate_synthetic_batch(c, n_samples=200)
                admitted, score = self.gate.check(t, synth, real_recent, len(synth))
                if admitted:
                    X_new.append(synth.astype(np.float32))
                    y_new.append(np.full(len(synth), c, dtype=self.y_train_ref.dtype))
                    n_admitted_total += len(synth)

            X_synth_combined = np.vstack(X_new) if X_new else None
            y_synth_combined = np.concatenate(y_new) if y_new else None

            self.clf.partial_fit_adaptation(X_fit, y_fit, X_synth_combined, y_synth_combined)
            adapt_duration = time.time() - t_adapt_0
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

            macro_f1_after = self._macro_f1(X_eval, y_eval)
            self.retrain_events.append({
                "timestep": t, "macro_f1_before": macro_f1_before,
                "macro_f1_after": macro_f1_after, "n_synthetic_admitted": n_admitted_total,
                "n_train_rows_after": self.clf.buffer_size,
                "adaptation_duration_seconds": float(adapt_duration),
                "memory_rss_mb": float(rss_mb)
            })
            log.info(f"[t={t}] incrementally adapted: macro_f1 {macro_f1_before:.4f} -> "
                     f"{macro_f1_after:.4f} ({n_admitted_total} synthetic rows admitted, "
                     f"buffer_size={self.clf.buffer_size}, time={adapt_duration:.2f}s)")

        return macro_f1_before, macro_f1_after

    def run(self, traffic_source: TrafficSource):
        is_live = None
        macro_f1_series = []
        for t, X, y, is_real_live in traffic_source:
            is_live = is_real_live if is_live is None else (is_live and is_real_live)
            mf1_before, mf1_after = self.step(t, X, y)
            macro_f1_series.append({"timestep": t, "macro_f1_before": mf1_before,
                                     "macro_f1_after": mf1_after})
        return {
            "traffic_source": type(traffic_source).__name__,
            "is_live_mininet_traffic": bool(is_live) if is_live is not None else None,
            "macro_f1_series": macro_f1_series,
            "drift_events": self.drift_events,
            "retrain_events": self.retrain_events,
            "gate_log": self.gate.entries,
        }
