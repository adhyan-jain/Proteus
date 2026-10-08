"""Synthetic-row operators for the intervention controller (SPEC v1.4).

Every generator implements `fit(X_c, c, rng)` / `sample(n, rng)` and sees ONLY the rows it is handed:
the controller passes the target class's real fit rows (D_fit_c). This module imports nothing from
`protocol`, `cache` or the partition code and has no code path to D_sel, D_gate, S_*, E_t or
unlabelled rows (a static test enforces that). The information set of a generator is therefore
D_ref plus D_fit_c, as in SPEC v1.1 D5.

Generators:
  RandomOversampler    duplicates real rows (the null generator: more weight, no new points)
  SMOTEGenerator       within-class interpolation between a row and one of its k nearest class
                       neighbours, k = min(5, n_c - 1) (about 30 lines on sklearn NearestNeighbors)
  MMDPrefilter         wraps a generator; admits its output for a class only if a
                       permutation-calibrated unbiased MMD cannot tell it apart from the real rows
                       (the legacy "fidelity gate" idea, calibrated instead of a fixed 0.25)

Negative controls (never methods; SPEC v1.4 section on controls):
  DonorSMOTE           SMOTE fitted on donor rows of ANOTHER class (e.g. BENIGN rows of D_ref) but
                       labelled as the target class: wrong-class synthetic data (NC1)
  GaussianBlob         class-conditional diagonal Gaussian with the class mean/std (NC2)
  FeatureShuffle       per-feature shuffle of the class rows, which destroys the joint structure (NC3)

`postprocess` clips to the per-feature [min, max] of the supplied bounds rows and, where the real
data is non-negative, forces non-negativity. SMOTE and oversampling are convex combinations/copies,
so they are inside the bounds already; the clip matters for the Gaussian control and for any
learned generator added later.
"""
import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

import numpy as np
from sklearn.neighbors import NearestNeighbors

from proteus.fidelity import compute_mmd


class GeneratorError(ValueError):
    pass


def postprocess(X, bounds):
    """Clip to the per-feature [min, max] of `bounds` and keep non-negative features non-negative."""
    X = np.asarray(X, dtype=np.float32)
    b = np.asarray(bounds, dtype=np.float32)
    lo, hi = b.min(axis=0), b.max(axis=0)
    out = np.clip(X, lo, hi)
    nonneg = lo >= 0.0
    out[:, nonneg] = np.maximum(out[:, nonneg], 0.0)
    return out.astype(np.float32, copy=False)


class _Base:
    name = "base"
    requires_gpu = False

    def __init__(self):
        self._X = None
        self._c = None

    def fit(self, X_c, c, rng):
        X_c = np.asarray(X_c, dtype=np.float32)
        if X_c.ndim != 2 or len(X_c) < 2:
            raise GeneratorError(f"{self.name}: need >= 2 real rows of class {c}, got {len(X_c)}")
        self._X, self._c = X_c.copy(), int(c)
        self._bounds = self._X
        self._fit(rng)
        return self

    def _fit(self, rng):
        pass

    def sample(self, n, rng):
        if self._X is None:
            raise GeneratorError(f"{self.name}: sample() before fit()")
        if n <= 0:
            return np.empty((0, self._X.shape[1]), dtype=np.float32)
        return postprocess(self._sample(int(n), rng), self._bounds)

    def _sample(self, n, rng):
        raise NotImplementedError

    @property
    def source_rows(self):
        """The exact rows the generator may draw from (used by the provenance tests)."""
        return self._X


class RandomOversampler(_Base):
    name = "ROS"

    def _sample(self, n, rng):
        return self._X[rng.integers(0, len(self._X), size=n)]


class SMOTEGenerator(_Base):
    name = "SMOTE"

    def _fit(self, rng):
        n = len(self._X)
        self.k = min(5, n - 1)
        nn = NearestNeighbors(n_neighbors=self.k + 1).fit(self._X)
        _, idx = nn.kneighbors(self._X)
        self._nbrs = idx[:, 1:]                      # drop the row itself

    def _sample(self, n, rng):
        i = rng.integers(0, len(self._X), size=n)
        j = self._nbrs[i, rng.integers(0, self.k, size=n)]
        lam = rng.random(size=(n, 1)).astype(np.float32)
        return self._X[i] + lam * (self._X[j] - self._X[i])


class DonorSMOTE(SMOTEGenerator):
    """NC1: SMOTE on rows of a DIFFERENT class (given at construction), labelled as the target."""
    name = "NC1_DONOR_SMOTE"

    def __init__(self, donor_X):
        super().__init__()
        self._donor = np.asarray(donor_X, dtype=np.float32)

    def fit(self, X_c, c, rng):
        if len(self._donor) < 2:
            raise GeneratorError("donor rows needed")
        super().fit(self._donor, c, rng)           # the target-class rows are deliberately unused
        return self


class GaussianBlob(_Base):
    name = "NC2_GAUSSIAN"

    def _fit(self, rng):
        self._mu = self._X.mean(axis=0)
        self._sd = self._X.std(axis=0)

    def _sample(self, n, rng):
        return self._mu + self._sd * rng.normal(size=(n, self._X.shape[1])).astype(np.float32)


class FeatureShuffle(_Base):
    name = "NC3_SHUFFLE"

    def _sample(self, n, rng):
        d = self._X.shape[1]
        out = np.empty((n, d), dtype=np.float32)
        for f in range(d):
            out[:, f] = self._X[rng.integers(0, len(self._X), size=n), f]
        return out


class MMDPrefilter:
    """Admit a class's synthetic batch only if it is statistically indistinguishable from the real
    rows: unbiased MMD^2 with a label-permutation p-value (n_perm permutations), admit iff
    p > p_min. A rejected batch is empty. Calibrated per call, not a fixed threshold (the legacy
    0.25 was chosen after seeing results, risk L7)."""
    requires_gpu = False

    def __init__(self, base, n_perm=100, p_min=0.05, probe=300):
        self.base = base
        self.name = f"{base.name}+MMD"
        self.n_perm, self.p_min, self.probe = n_perm, p_min, probe
        self.admitted = None
        self.last_p = None

    @property
    def source_rows(self):
        return self.base.source_rows

    def fit(self, X_c, c, rng):
        self.base.fit(X_c, c, rng)
        real = self.base.source_rows
        syn = self.base.sample(min(len(real) * 4, self.probe),
                               np.random.default_rng(int(rng.integers(1 << 31))))
        real_s = real[rng.permutation(len(real))[: self.probe]]
        obs = compute_mmd(syn, real_s, unbiased=True, standardize=True)
        pooled = np.vstack([syn, real_s])
        n_syn = len(syn)
        ge = 0
        for _ in range(self.n_perm):
            perm = rng.permutation(len(pooled))
            ge += compute_mmd(pooled[perm[:n_syn]], pooled[perm[n_syn:]], unbiased=True,
                              standardize=True) >= obs
        self.last_p = float((1 + ge) / (self.n_perm + 1))
        self.admitted = self.last_p > self.p_min
        return self

    def sample(self, n, rng):
        if self.admitted is None:
            raise GeneratorError("sample() before fit()")
        if not self.admitted:
            return np.empty((0, self.base.source_rows.shape[1]), dtype=np.float32)
        return self.base.sample(n, rng)


GENERATORS = {"ROS": RandomOversampler, "SMOTE": SMOTEGenerator, "NC2_GAUSSIAN": GaussianBlob,
              "NC3_SHUFFLE": FeatureShuffle}
