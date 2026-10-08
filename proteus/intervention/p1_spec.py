"""SPEC v1.4 preregistration constants (P1 campaign) and the hash of the normative rules text.

`protocol.SPEC_VERSION` stays "1.3": it names the PARTITION/P0 protocol, feeds the manifest and P0
parameter digests, and must not change or the frozen P0 artifacts could not be reproduced and the P1
manifests for seeds 0-4 would no longer equal P0's. `P1_SPEC_VERSION` names the P1 rules. The
normative text is docs/INTERVENTION_SPEC.md between the P1-PREREGISTRATION markers; its SHA-256
travels with every P1 result, exactly like P0's rules hash.
"""
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from proteus.intervention.provenance import REPO_ROOT

P1_SPEC_VERSION = "1.4"
SPEC_PATH = REPO_ROOT / "docs" / "INTERVENTION_SPEC.md"
_BEGIN, _END = "<!-- P1-PREREGISTRATION:BEGIN -->", "<!-- P1-PREREGISTRATION:END -->"

MAIN_ARMS = ("FROZEN", "REAL_ONLY", "CTRL-ROS", "CTRL-THRESH", "CTRL-SMOTE", "FIXED-SMOTE-1",
             "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE")
CONTROL_ARMS = ("NC1-DONOR-SMOTE", "NC2-GAUSSIAN", "NC3-SHUFFLE", "NC4-PLACEBO-DDOS")
ABLATION_ARMS = ("ABL-NO-STEP-TEST", "ABL-I-EQ-A", "ABL-NO-STEP-SAFETY", "ABL-KMAX1", "ABL-MMD",
                 "ABL-POOLED", "ABL-NO-CANARY-CTRL", "ABL-NO-CANARY-REAL")
REFERENCE_ARMS = ("REAL_ONLY_ALL_LABELS", "ORACLE_DOSE")
ALL_ARMS = MAIN_ARMS + CONTROL_ARMS + ABLATION_ARMS + REFERENCE_ARMS


def rules_text(path=SPEC_PATH):
    text = Path(path).read_text()
    if _BEGIN not in text or _END not in text:
        raise RuntimeError(f"{path} has no P1-PREREGISTRATION section")
    return text.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()


def rules_sha256(path=SPEC_PATH):
    return hashlib.sha256(rules_text(path).encode()).hexdigest()


@dataclass(frozen=True)
class P1Criteria:
    """Constants of the P1 preregistration. Do not tune after any P1 result exists."""
    scenario: str = "S1"
    budget: int = 100
    seeds: tuple = tuple(range(10))
    p0_paired_seeds: tuple = (0, 1, 2, 3, 4)
    ci_level: float = 0.95                 # two-sided paired t-interval over seeds
    activity_min_seeds: int = 6            # H4: >= 6 of 10 seeds with a promoted th* (star branch)
    fixed_rhos: tuple = (1.0, 4.0)
    thresh_ladder: tuple = (1.0, 2.0, 4.0, 8.0, 16.0)
    mmd_p_min: float = 0.05
    mmd_n_perm: int = 100
    donor_rows: int = 1000
    degenerate_k0_share: float = 0.8       # F8
    rollback_share_max: float = 0.2        # F4
    arms: tuple = ALL_ARMS
    sequence: tuple = ("H2", "H3a", "H3b", "H5")

    def digest(self):
        payload = json.dumps({"p1_spec_version": P1_SPEC_VERSION, "criteria": asdict(self)},
                             sort_keys=True, default=list)
        return hashlib.sha256(payload.encode()).hexdigest()
