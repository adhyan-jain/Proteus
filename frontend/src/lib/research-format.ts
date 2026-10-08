import type { CI } from "./research";

export const fx = (x: number | null | undefined, d = 3) =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : x.toFixed(d);

export const ciStr = (ci: CI | undefined, d = 3) =>
  !ci || ci.mean === null ? "—" : `${fx(ci.mean, d)} [${fx(ci.lo, d)}, ${fx(ci.hi, d)}]`;

export const ARM_LABEL: Record<string, string> = {
  FROZEN: "Frozen (no adaptation)",
  REAL_ONLY: "Real-only adaptation",
  "CTRL-ROS": "Controller · duplication",
  "CTRL-THRESH": "Controller · threshold shift",
  "CTRL-SMOTE": "Controller · SMOTE (proposed)",
  "FIXED-SMOTE-1": "Fixed dose SMOTE ρ=1",
  "FIXED-SMOTE-4": "Fixed dose SMOTE ρ=4",
  "ALWAYS-SMOTE": "Always-on SMOTE ρ=1",
  "FIDGATE-SMOTE": "Fidelity-gated SMOTE ρ=4",
  "NC1-DONOR-SMOTE": "NC1 wrong-class rows",
  "NC2-GAUSSIAN": "NC2 Gaussian blob",
  "NC3-SHUFFLE": "NC3 feature shuffle",
  "NC4-PLACEBO-DDOS": "NC4 placebo dose (DDoS)",
  "ABL-NO-STEP-TEST": "Ablation · no step test",
  "ABL-I-EQ-A": "Ablation · no need test (I := A)",
  "ABL-NO-STEP-SAFETY": "Ablation · no step safety",
  "ABL-KMAX1": "Ablation · K_max = 1",
  "ABL-MMD": "Ablation · + MMD pre-filter",
  "ABL-POOLED": "Ablation · pooled sel/gate",
  "ABL-NO-CANARY-CTRL": "Ablation · controller, no canary",
  "ABL-NO-CANARY-REAL": "Ablation · real-only, no canary",
  REAL_ONLY_ALL_LABELS: "Reference · all labels (P0 control)",
  ORACLE_DOSE: "Reference · oracle dose (never deployed)",
};
export const armLabel = (a: string) => ARM_LABEL[a] ?? a;

export const REASON_LABEL: Record<string, string> = {
  promoted: "promoted",
  no_affected_region: "no affected region",
  utility_no_gain: "utility: no gain",
  utility_inconclusive: "utility: inconclusive",
  utility_unmeasurable: "utility: unmeasurable",
  envelope_inconclusive: "envelope: inconclusive",
  envelope_violated: "envelope: violated",
  envelope_unverifiable: "envelope: unverifiable",
  sanity: "sanity",
};

export const fmtSec = (s: number | null | undefined) =>
  s === null || s === undefined ? "—" : s < 90 ? `${s.toFixed(0)} s` : `${(s / 60).toFixed(1)} min`;
