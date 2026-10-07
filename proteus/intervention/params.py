"""Every frozen threshold of SPEC v1.0, section 1.5, in one place.

Nothing else in `proteus.intervention` may hard-code a threshold. Changing a default here changes
the experiment and must bump `protocol.SPEC_VERSION` (spec anti-leakage rule 7); a test pins the
defaults to the spec so an accidental edit fails loudly.
"""
import proteus.config  # noqa: F401 -- must import before numpy/sklearn to cap BLAS/OMP threads

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Optional

from proteus.intervention.protocol import SPEC_VERSION


@dataclass(frozen=True)
class InterventionParams:
    # --- error control -------------------------------------------------------------------
    alpha: float = 0.05            # one-sided; promotion tests use alpha/2, steps alpha/k_max
    n_boot: int = 2000             # R: paired, class-stratified bootstrap resamples
    # --- measurability / region ----------------------------------------------------------
    s_min: int = 5                 # min class support in D_sel and D_gate to be measurable
    n_min: int = 5                 # min real fit rows of a class before a generator may be fit
    eps_def: float = 0.05          # deficiency floor (F1 scale)
    # --- safety envelope -----------------------------------------------------------------
    eps_s: float = 0.01            # max stable-class macro-F1 drop (UCB)
    eps_fpr: float = 0.005         # max benign false-positive-rate increase (UCB)
    benign_label: str = "BENIGN"   # name of the benign class in ControllerView.class_names
    # --- controller-only values (frozen now, unused until step 6) -------------------------
    eta: float = 0.02              # step cost: smallest marginal gain justifying one dose step
    eps_ni: float = 0.01           # non-inferiority margin of theta* against theta_R
    rho_ladder: tuple = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)
    m_cap: int = 2000
    phi_max: float = 0.5
    k_max: int = 10
    # --- learner ---------------------------------------------------------------------------
    rf_n_estimators: int = 100
    rf_max_depth: Optional[int] = None

    @property
    def promotion_alpha(self):
        return self.alpha / 2.0

    @property
    def step_alpha(self):
        return self.alpha / self.k_max

    def digest(self):
        payload = json.dumps(asdict(self), sort_keys=True, default=list)
        return hashlib.sha256(f"{SPEC_VERSION}|{payload}".encode()).hexdigest()
