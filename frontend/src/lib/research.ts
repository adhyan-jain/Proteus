// Typed client for the read-only research endpoints (api/research.py). Every value is a verbatim
// view of a file under results/ (with its sha256); non-finite floats arrive as null = "not measurable".
import { get, type NotAvailable } from "./api";

export type CI = { mean: number | null; lo: number | null; hi: number | null; n: number; half_width: number | null };
export type Paired = {
  diff: CI;
  per_seed: Record<string, number | null>;
  a_mean: number | null;
  b_mean: number | null;
};
export type Hypothesis = Paired & { rejected: boolean; contrast: string; tested_under_sequence?: boolean };
export type Artifact = { file: string; sha256: string; bytes: number; modified: number };

export type ArmRow = {
  r_recovery: CI;
  r_recovery_matched: CI;
  shadow_candidate: CI;
  shadow_real_only_candidate: CI;
  v13_auc: CI;
  promotions: { star: number; real_only: number; rollbacks: number; canary_checks: number; seeds_with_star: number };
  safety: { breaches: number; worst_stable_f1_drop: number; worst_benign_fpr_increase: number; nonbase_windows: number };
  tallies: Record<string, number>;
  wall_clock_s: number;
  candidate_fits: number;
};

export type P1Doc = {
  kind: "p1_summary";
  p1_spec_version: string;
  git_sha: string;
  git_dirty: boolean;
  analysed_utc: string;
  budget: number;
  criteria_digest: string;
  class_names: string[];
  primary_endpoint: string;
  provenance: {
    seeds_present: number[];
    complete: boolean;
    all_preregistered: boolean;
    git_shas: string[];
    git_dirty_any: boolean;
    p1_spec_version: string[];
    p1_rules_sha256: string[];
    p1_rules_sha256_now: string;
    p1_criteria_digest: string[];
    params_digest: string[];
    repairable_set_R: number[];
    repairable_set_names: string[];
    manifest_matches_p0: Record<string, boolean | null>;
    v1_violations: Record<string, number>;
    versions: Record<string, string>;
  };
  p0_reconciliation: { seeds: number[]; identical: boolean; problems: { seed: number; t: number }[]; note: string };
  arm_table: Record<string, ArmRow>;
  hypotheses: {
    H2: Hypothesis;
    H3a: Hypothesis;
    H3b: Hypothesis;
    H5: {
      per_fixed: Record<string, Paired & { noninferior: boolean; established_inferior: boolean }>;
      tested_under_sequence: boolean;
      noninferior_to_all: boolean;
    };
    H4: {
      s_report_breaches: number;
      seeds_with_star_promotion: number;
      activity_required: number;
      passed: boolean;
      safe_by_inaction: boolean;
    };
  };
  flags: Record<string, boolean>;
  flag_details: Record<string, unknown>;
  negative_controls: Record<string, Paired & { beats_real_only: boolean }>;
  ablations: Record<string, { vs_ctrl_smote: Paired; vs_real_only: Paired }>;
  references: Record<string, { vs_real_only: Paired }>;
  main_arms_vs_real_only: Record<string, Paired>;
  shadow_vs_real_only: Record<string, Paired>;
  step_filter_diagnostics: Record<string, number>;
  pre_drift_probe: { windows: number; nonempty_region: number; promoted: number };
  curves_r_f1_by_post_window: Record<string, { mean: number[]; sd: number[] }>;
  per_seed: Record<string, Record<string, Record<string, unknown>>>;
  verdict: { branch: string; p2_unlocked: boolean; fired_flags: string[]; complete_and_preregistered: boolean };
};

export type DecisionRow = {
  t: number;
  region: number[];
  eligible: number[] | null;
  k: number | null;
  stop_reason: string | null;
  branch: string | null;
  reason: string | null;
  star_reason: string | null;
  promoted: boolean | null;
  doses: Record<string, number> | null;
  n_syn: number | null;
  canary: string | null;
  rollback: boolean;
  deployed_is_base: boolean;
  search: {
    k: number;
    accepted: number | null;
    candidates: {
      c: number;
      rung: number;
      n_syn_after: number;
      gain_lcb: number | null;
      gain_point: number | null;
      safe: boolean;
      d_fpr_sel_ucb: number | null;
      d_stable_s_ucb: number | null;
      d_fpr_s_ucb: number | null;
    }[];
  }[];
};
export type DecisionsDoc = { class_names: string[]; traces: Record<string, Record<string, DecisionRow[]>> };

export type P0Doc = {
  spec_version: string;
  git_sha: string;
  scenario: string;
  seeds: number[];
  budgets: number[];
  conditions: string[];
  preregistered_configuration: boolean;
  spec_rules_sha256: string;
  criteria_digest: string;
  params_digest: string;
  h1: { outcome: string; scope: string; budget_statuses: Record<string, string>; validity_all_pass: boolean };
  validity: {
    v1_leakage_audit: { pass: boolean; n_runs_audited: number; n_run_violations: number; n_cross_pool_group_overlaps_informational: number };
    v3_integrity: { pass: boolean; n_cells_checked: number; violations: unknown[] };
    v4_repairability: {
      pass: boolean;
      repairable_set: number[];
      budget_independent: boolean;
      per_budget: Record<
        string,
        { per_class_seed_counts: Record<string, { repaired: number; residual_deficiency: number; thin_real_support: number; unmeasurable: number }> }
      >;
    };
  };
  diagnostics: {
    v2_null_region: { pass: boolean; gates_p0_outcome: boolean };
    label_ambiguity: {
      go_classes: Record<string, { seeds_with_go_cell: number; max_d_sel_share: number; max_e_share: number; possibly_ambiguity_driven: boolean }>;
      threshold_eps_def: number;
    };
  };
  data_adequacy: {
    per_budget: Record<
      string,
      {
        status: string;
        n_seeds_with_go: number;
        n_seeds_assessable: number;
        per_seed: Record<string, { n_cells: number; n_assessable: number; n_go: number; go_classes: number[] }>;
      }
    >;
  };
  aggregate_by_budget: Record<string, { recovery_auc: Record<string, CI>; n_promotions: Record<string, CI> }>;
  data: {
    n_rows: number;
    n_features: number;
    class_names: string[];
    class_counts: Record<string, number>;
    rows_per_day: Record<string, number>;
    label_conflicts: Record<string, number>;
  };
  params: Record<string, unknown>;
  criteria: Record<string, unknown>;
};

export type ArtifactsDoc = {
  available: true;
  artifacts: { key: string; file: string; exists: boolean; sha256?: string; bytes?: number }[];
  p1_seed_files: string[];
};
export type StagesDoc = {
  available: true;
  stages: Record<string, unknown> & {
    gates: { p2_unlocked: boolean | null; p1_branch: string | null };
  };
};

export type VerificationDoc = {
  generated_utc: string;
  git_sha: string;
  commands: { command: string; result: string; passed: number | null; failed: number | null; skipped: number | null }[];
  notes: string[];
};

type Ok<T> = { available: true; artifact: Artifact; doc: T };

export const research = {
  p0: () => get<Ok<P0Doc> | NotAvailable>("/api/research/p0"),
  p0s2: () => get<Ok<P0Doc> | NotAvailable>("/api/research/p0/s2"),
  p1: () => get<Ok<P1Doc> | NotAvailable>("/api/research/p1"),
  decisions: () => get<Ok<DecisionsDoc> | NotAvailable>("/api/research/p1/decisions"),
  artifacts: () => get<ArtifactsDoc>("/api/research/artifacts"),
  stages: () => get<StagesDoc>("/api/research/stages"),
  verification: () => get<Ok<VerificationDoc> | NotAvailable>("/api/research/verification"),
};

export const isOk = <T,>(x: Ok<T> | NotAvailable): x is Ok<T> => x.available === true;
