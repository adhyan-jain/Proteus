# Proteus — Frozen Research Specification: Feedback-Controlled Synthetic Intervention (SPEC v1.3)

## v1.3 changes (supersede any conflicting v1.0–v1.2 text below; §1.5 thresholds are unchanged)

v1.3 is a one-item amendment to the envelope rejection taxonomy (D3). It was made after the real-data
cache existed and a single-seed, non-preregistered smoke run (S1, B=25, seed 0) had been executed,
and before any preregistered P0 result existed, so nothing has to be rerun. The smoke run showed
that `envelope_violated` was assigned from a *point estimate* at tiny sample sizes: with 28–38
benign rows in D_gate, one flipped row moves the empirical benign-FPR by 1/28 ≈ 3.6 percentage
points, 7× the preregistered ε_FPR = 0.005, even though the data cannot establish a degradation
beyond ε (the upper bound rejected the candidate correctly, but the label read "unsafe").

- **F1 — an envelope check is `violated` only when the violation is statistically established.**
  For each envelope quantity q (stable macro-F1 drop on S_gate, benign-FPR rise on S_gate,
  benign-FPR rise on D_gate's benign rows), with its preregistered ε (ε_S or ε_FPR, §1.5) and the
  one-sided level α/2 used for promotion, over the same paired class-stratified bootstrap
  replicates as before:
  - **PASS** (`ok`): UCB_{α/2}(q) ≤ ε. This is the only state that can be promoted.
  - **VIOLATED**: LCB_{α/2}(q) > ε — degradation beyond ε is statistically established.
  - **UNVERIFIABLE**: a bound is undefined (e.g. no benign rows). Fails closed, as before.
  - **INCONCLUSIVE**: UCB_{α/2}(q) > ε and LCB_{α/2}(q) ≤ ε — the evidence cannot establish
    either safety or violation.
  The labels are exhaustive and mutually exclusive per quantity. The reason for a rejected
  candidate keeps the precedence violated > unverifiable > inconclusive (v1.1, D3). The point
  estimate no longer decides any label; it is still reported.
- **Decisions are unchanged.** A candidate is promoted iff its utility criterion passes and *every*
  envelope quantity is PASS (UCB ≤ ε); v1.3 only relabels rejections between `envelope_violated`
  and `envelope_inconclusive`. Residual-set construction, budget cells, the P0 decision procedure
  (§L.1 is byte-identical to v1.2; its SHA-256 is unchanged), leakage rules, partitions, model
  inputs, every numerical ε, the seed set, the budgets and the scenario definitions are untouched.
  The utility labels (`utility_no_gain` is still assigned from the point gain) are out of scope of
  this amendment and are not changed.
- **Raw quantities stay in the output.** Each candidate report carries, per quantity: the sample
  sizes (`n_gate_benign`, `n_s_gate_benign`, `n_s_gate_rows`, `n_stable_classes`), the point
  estimate, `…_lcb` and `…_ucb`, the preregistered ε (`eps_stable_f1`, `eps_fpr`), the level
  (`envelope_alpha`) and the resulting label.

## v1.2 changes (supersede any conflicting v1.0/v1.1 text below; §1.5 thresholds are unchanged)

v1.2 freezes the P0 decision procedure. It was written after the Step 4 tooling existed but before
the real-data cache was built and before any P0 result existed, so nothing has to be rerun. The
rules previously lived in the approved review plan and in `validity.py`; a hostile reviewer must be
able to read them here, so they are now normative in §L.1 (`protocol.SPEC_VERSION = "1.2"` feeds the
manifest and params digests; a `criteria_digest` and the SHA-256 of §L.1 travel with every result).
No §1.5 threshold changes; the new rules use only counts already in the review plan (2 windows,
3-of-5 and 4-of-5 seeds) and the frozen ε_def and n_min.

- **E1 — one status per budget, no global precedence.** Every budget is classified independently as
  GO, NO_ROOM or UNMEASURABLE by one criterion: *could the preregistered GO criterion have been met
  there?* GO is a subset of "assessable", so the three statuses partition the budgets; there is no
  precedence question and no pooled unmeasurable-rate veto (the old ">80% of cells unmeasurable"
  rule is now a descriptive statistic only).
- **E2 — V3 is split.** *Integrity* (validity): every measurable drift class must be in the frozen
  model's affected region (FROZEN cannot predict a class absent from D_ref, so an exception is a
  pipeline defect) → any violation is INVALID. *Data adequacy* (not validity): insufficient
  support makes a budget UNMEASURABLE, never INVALID. Both are reported.
- **E3 — V2 is a mandatory diagnostic that never gates the P0 outcome.** A non-empty pre-drift
  affected region can come from a reservoir-scale θ_base missing rare *pre-drift* classes, which
  cannot create a GO. A failed V2 blocks P1 and any later claim until a spec revision defines how
  pre-existing deficiency enters A, U and I.
- **E4 — V4 is class-wise.** The positive control defines a *repairable set* R of drift classes
  that abundant labels actually repair. V4 passes iff R ≠ ∅ (and R is identical at every budget).
  A GO may count only classes in R; classes outside R are reported as unrepaired and can never
  generate a GO.
- **E5 — V1 keeps cross-pool duplicates legal** and adds reporting that never gates the outcome:
  rows of the learning buffers duplicated in stable-evaluation partitions, and feature vectors that
  carry different labels across temporal pools, with an ambiguity flag on GO classes. Contradictory
  vectors can be intrinsically unrepairable, so a flagged GO requires interpretation.
- **E6 — budget scope.** V1, integrity, adequacy and V4 are evaluated at every budget (the old
  "V3 at some budget" rule is removed). Budgets are nested on a matched seed (checked, part of V1).
- **E7 — INCONCLUSIVE_MIXED is removed.** B=25 UNMEASURABLE with B=100 NO_ROOM is reported as
  "NO_ROOM at B=100; B=25 unmeasurable" and the budget-grid conclusion is NO_GO_NO_ROOM on the
  assessed budget. The only INCONCLUSIVE outcome is "no budget assessable".
- **E8 — provenance.** Results carry `spec_version`, `criteria_digest` (the constants of §L.1),
  `spec_rules_sha256` (the text of §L.1), the params digest, manifest digests and git SHA, and
  keep validity, diagnostics, data adequacy and outcome in separate, ordered blocks.

## v1.1 changes (supersede any conflicting v1.0 text below; §1.5 thresholds are unchanged)

v1.1 corrects validity problems found while reviewing the Step 3 implementation. It was written
before any P0 result existed, so nothing had to be rerun. `protocol.SPEC_VERSION` is "1.1" and
feeds both the manifest digest and the parameter digest, so v1.0 and v1.1 artifacts cannot be
mixed.

- **D1 — base model.** θ₀ := fit(D_ref), with the same learner, hyperparameters and
  `random_state` as every candidate. TRAIN is only the population D_ref is drawn from.
  Rationale: under v1.0, θ_R − θ₀ confounded the new real data with a ~60× reduction in training
  data (TRAIN → D_ref), which would show up as spurious stable-traffic degradation. With
  θ₀ = fit(D_ref) and θ_R = fit(D_ref ∪ D_real) the real-only comparison is strictly nested, and
  later synthetic conditions nest on top (D_ref ⊂ D_ref ∪ D_real ⊂ D_ref ∪ D_real ∪ D_syn).
  Cost: the base model is reservoir-scale, weaker on rare pre-drift classes than a model fit on
  all of TRAIN; reports must say so. Implemented as `CandidateBuilder.build_base(view)`; the
  free-form initial-model path is removed.
- **D2 — fixed safety anchor.** All three envelope criteria (stable macro-F1 drop on S_gate,
  benign-FPR increase on S_gate, benign-FPR increase on D_gate's benign rows) compare the
  candidate with θ_base = fit(D_ref), fixed for the whole run, not with the current incumbent.
  The utility criterion still compares the candidate with the current incumbent. Rationale: under
  the oracle trigger the incumbent is replaced up to ~10 times; measuring safety against the
  moving incumbent lets stable degradation accumulate to ~10 ε while every step passes.
  Carried in `DecisionContext.anchor` (a model, not data).
- **D3 — rejection taxonomy** (decision logic unchanged, every rejection still rejects, unverifiable
  fails closed): `sanity`, `no_affected_region`, `utility_unmeasurable` (no D_gate evidence or no
  bound), `utility_no_gain` (point gain <= 0), `utility_inconclusive` (point gain > 0 but LCB <= 0),
  `envelope_unverifiable` (a quantity is undefined, e.g. no benign rows), `envelope_violated`
  (point estimate of a degradation > its epsilon), `envelope_inconclusive` (point estimates within
  epsilon but a UCB above it). Precedence among envelope labels: violated > unverifiable >
  inconclusive (a known violation outranks missing evidence); every failing criterion is
  listed. The report also records the support counts behind each statistic.
- **D4 — residual eligibility uses recall.** I = {c ∈ A : LCB_α(1 − Recall_c(θ_R; D_sel)) > ε_def
  ∧ n_c ≥ n_min}. F1 deficiency is kept for A and U (collateral harm should count there) but not
  for I: adding rows of class c repairs c's recall, not other classes' leakage into c, and an
  F1-based I could report a spurious "residual deficiency" (e.g. BENIGN, polluted by an unseen
  attack predicted as benign). The F1-based set is logged as a diagnostic only.
- **D5 — generator information set (specification only; no generator code yet).** Every
  generator, including WGAN-GP pretraining and its normalisation statistics, may use only D_ref
  plus the target class's D_fit rows. No TRAIN-wide pretraining: it would give synthetic
  conditions pre-drift information REAL_ONLY never has, confounding H2 and F7.

## Context

The current Proteus headline (closed-loop 0.1738 vs. baseline 0.0294 final macro-F1, S1 Mon–Thu→Fri)
does **not** show that synthetic data helps. `results/gan_ablation.json` (seed 0) shows real-only
incremental adaptation does as well or better: post-drift mean 0.1575 for real only, 0.1507 with
gated GAN, 0.1407 with ungated GAN. `results/gan_downstream_utility.json` condition D (gated GAN)
is bit-identical to real-only, because the gate rejected everything. The 5.91× comes entirely from
giving the adapter oracle labels for 70% of every post-drift window.

The question we are now asking is narrower and can be falsified: **after real-only adaptation
under a realistic label budget, is there residual per-class deficiency? If so, can a
sequential, utility-gated synthetic dose controller reduce it without breaking a stable-traffic
safety envelope, and do better than real-only, plain oversampling, and fixed-dose synthetic?** We
claim no novelty. The spec freezes the protocol, the math, the API, and the falsification
criteria before any code is written.

---

## A. Reusable infrastructure (audit result)

| Component | File | Verdict |
|---|---|---|
| CICIDS2017 load/clean | `proteus/data_full.py::load_cicids2017_raw`, `clean_and_unify_cicids2017`, `get_feature_schema` | **Reuse as is** |
| Day-split loader | `proteus/evaluate_full.py::_load_day_split_data` | Reuse the pattern. A new loader must also keep `timestamp` and add a row-hash column |
| Bounded-buffer RF | `proteus/closed_loop_full.py::BoundedBufferClassifier` | Reuse the logic **through composition**. Its FIFO lets synthetic rows evict real rows, so the controller needs a separate synthetic slot that is rebuilt each run |
| KS drift test | `proteus/drift.py::detect_drift` | Reuse. Its reference must be held out (see L2) |
| MMD | `proteus/fidelity.py::compute_mmd(unbiased=True)` | Reuse only as an optional ablation pre-filter, with a permutation-calibrated threshold. The fixed 0.25 is not used |
| WGAN-GP | `proteus/gan_full.py::WGANGPFull`, `train_one_epoch`, `generate_synthetic_batch` | Reuse the classes. The **checkpoint is contaminated (L1)** and must be retrained on pre-drift data only, with all 25 label slots reserved |
| Per-class breakdown | `proteus/evaluate_full.py::_per_class_breakdown` | Reuse |
| Release/hot-swap/rollback | `release_manager.py`, `model_manager.py`, `drift_daemon.py` | **Infrastructure only.** Not used for research evidence |
| SDN path | `sdn/topology/*`, `api/server.py /predict` | **Infrastructure only.** 39 of 52 features are defaulted to 0, so live OpenFlow can't produce evidence for this question |

`imblearn` is not installed. SMOTE will be written in-house on `sklearn.neighbors.NearestNeighbors`
(about 30 auditable lines, no new dependency).

## B. Current leakage and rigor risks

| ID | Risk | Where | Severity |
|---|---|---|---|
| L1 | The WGAN-GP was trained on a stratified **all-days** split, so it saw Friday `Bot` rows. Its normalisation stats include Friday too. Every drift experiment that uses this checkpoint is contaminated, including static augmentation | `gan_full.run_stage2` → `load_data_full` | **High** |
| L2 | The drift reference confidences are computed **in-sample** on training rows, so the KS test is biased | `closed_loop_full.py:203`, `validate_full.py:94` | High |
| L3 | About 76.8% of pre-drift eval rows were also training rows (already documented) | `evaluate_full.run_one_seed` | High (pre-drift numbers) |
| L4 | Each window is sampled independently with replacement across windows, so a Friday row can land in E_t and also in F_t′. CICIDS2017 also has exact-duplicate feature vectors, so disjoint indices can still leak through identical rows | `RealDataReplaySource.__iter__` | **High** |
| L5 | The adapter fits on F_t and is scored on E_t of the **same** window. That assumes zero label latency, which is optimistic | `ClosedLoopOrchestrator.step` | Medium |
| L6 | Oracle labels for 70% of each window leave real-only recovery nothing to do, so synthetic data cannot show a benefit | protocol | **High (validity of the question)** |
| L7 | The MMD threshold 0.25, `GAN_ADMIT_CLASSES` and the over-dispersion exclusions were all chosen **after** seeing the results they are validated on | `fidelity`, `gan_full` | Medium |
| L8 | The Stage 3 test split is a stratified random split across days, so near-duplicates sit in both train and test. 0.892 is an in-distribution number, not a temporal one | `load_data_full` | Medium (claims) |
| L9 | `split_rng=123` and RF `random_state=42` stay fixed across seeds. The CI uses z=1.96 at n=5; it should be t₄=2.776 | `evaluate_full.py:127,226` | Medium (rigor) |
| L10 | The daemon retrains on its **own predictions** (pseudo-labels, which reinforce its own mistakes). Its canary counts "conf<0.10" as an error with no labels. Its validation floor is accuracy ≥0.35 | `drift_daemon.py` | Infra only, but no evidence may cite it |
| L11 | Headline 25-class macro-F1 with zero-division is dominated by which classes have support | reporting | Metric artifact |
| L12 (future) | Reusing controller validation data across sequential steps causes winner's-curse overfitting | new controller | Prevented by the sel/gate split below |
| L13 | `LabelEncoder` is fit on all labels, including Friday ones. Only the taxonomy leaks, not data | loaders | Declared and allowed |

---

## 1. Frozen technical specification

### 1.1 Scenarios
- **S1 (pilot + main):** pre-drift = Mon–Thu, drift = Friday (new classes: Bot, Bot-Attempted, DDoS, PortScan).
- **S2 (main study only):** pre-drift = Mon+Tue, drift = Wed (DoS Hulk/GoldenEye/slowloris/Slowhttptest/Heartbleed and their attempted variants).
- Inside each drift day, rows are shuffled so the post-drift period is stationary with one step change. Time-ordered replay is a later robustness arm and is out of scope here.

### 1.2 Per-seed data partition (group-disjoint, frozen once per seed, written to a manifest)
Every row gets a group id `g = blake2b(float32 feature bytes)`. **All partitioning is done on
groups**, so identical feature vectors never cross a partition boundary.

- Pre-drift pool → `TRAIN` (v1.1: source of the D_ref reservoir only; θ₀ := fit(D_ref)) | `S_cal` (KS reference, 20k) | `S_sel` (20k) | `S_gate` (20k) | `S_report` (20k) | `PRE_STREAM` (pre-drift windows).
- Drift pool → split into **disjoint, non-replacing** window blocks W_t of 3000 rows.
- Each W_t → `E_t` (30%, reporting only) | `U_t` (unlabelled rest) | `L_t` (label budget B rows, drawn uniformly from the non-E rows).
- Labelled rows L_t go to `fit` / `sel` / `gate` in a 0.6/0.2/0.2 ratio by group hash, and stay there for good.
- A single seed drives the window draws, the partitions, RF `random_state`, the generator RNG and the bootstrap RNG.

### 1.3 Timeline per window t (prequential, label delay = 1)
1. The deployed θ predicts W_t. E_t is scored and logged. **Nothing is learned from E_t.**
2. Confidences from W_t feed the KS detector (reference = θ's confidences on `S_cal`).
3. Labels of L_{t−1} arrive. **Canary:** if a promotion happened at t−1, the new θ and the shadow θ_prev are both scored on L_{t−1}, and the rollback rule (J.2) is applied.
4. L_{t−1} is assigned to fit, sel or gate, and the buffers are updated.
5. If an episode is active, the controller runs (Section 2) and returns a promotion decision. The chosen model is deployed from t+1.
- **Trigger mode:** the pilot uses an *oracle trigger*, with episodes active for every post-drift window, so that detection errors are kept separate from controller behaviour. KS-triggered mode (α=0.01) is a secondary arm, and its pre-drift false-trigger rate is reported.

### 1.4 Learner
RF with 100 trees, `random_state=seed`, `n_jobs=DEFAULT_N_JOBS`. The base model (v1.1) is
θ_base = θ₀ = fit(D_ref) and is fixed for the whole run. A candidate's training set =
`D_ref` (20k reservoir from TRAIN) ∪ `D_real` (sliding real buffer, all fit rows, capped at 5k, FIFO) ∪ `D_syn` (synthetic slot, **rebuilt from scratch on every controller run, never persisted, never in the FIFO**).

### 1.5 Frozen parameters (changing any one bumps the SPEC version)
| Symbol | Value | Meaning |
|---|---|---|
| B | pilot {25, 100}; main {25, 100, 400} | labels per window |
| s_min | 5 | minimum class support in D_sel or D_gate for that class to be measurable |
| n_min | 5 | minimum real fit rows of a class before its generator may be fit |
| ε_def | 0.05 | deficiency floor (on the F1 scale) |
| η | 0.02 | step cost: the smallest marginal gain that justifies one more dose step |
| ε_ni | 0.01 | non-inferiority margin of θ* against θ_R at the gate |
| ε_S | 0.01 | maximum stable-class macro-F1 drop (UCB) |
| ε_FPR | 0.005 | maximum benign false-positive-rate increase (UCB) |
| ρ ladder | {0, 0.5, 1, 2, 4, 8} | synthetic-to-real ratio per class |
| M_cap | 2000 | maximum synthetic rows per class |
| φ_max | 0.5 | maximum synthetic share of (D_real ∪ D_syn) |
| K_max | 10 | maximum accepted dose steps per controller run |
| α | 0.05 one-sided; step tests use α/K_max | error control |
| R | 2000 | paired, class-stratified bootstrap resamples |

---

## 2. Mathematical definitions

Notation: θ is a classifier and 𝒟 is a labelled set. F1_c(θ;𝒟) is the one-vs-rest F1 of class c.
For any statistic Δ, LCB_a / UCB_a are the a / (1−a) percentiles of its paired bootstrap
distribution over 𝒟. Both models are scored on the same resampled rows, and resampling is
stratified by true class.

**C. State variables.** At controller run τ the state is
s_τ = (θ₀, D_ref, D_real, D_sel, D_gate, S_sel, S_gate, n⃗, A, I, ρ⃗, k, φ), where
- θ₀ is the deployed model;
- n_c = |{x ∈ D_fit : y = c}| is the real fit count per class;
- A is the affected region and I the intervention-eligible set (defined below);
- ρ⃗ is the current dose vector, k the number of accepted steps, and φ = |D_syn| / (|D_real| + |D_syn|).

Logged drift descriptors (not decision inputs): the KS statistic, a χ² test on the shift in the
predicted-label distribution, novel-class flags (c ∉ labels(D_ref)), and the per-class
deficiency vector.

**Measurability.** M = {c : support_c(D_sel) ≥ s_min ∧ support_c(D_gate) ≥ s_min}.
No intervention is made on a class whose utility cannot be measured.

**Deficiency.** d_c(θ) = 1 − F1_c(θ; D_sel).

**Affected region.** A = {c ∈ M : LCB_α(d_c(θ₀)) > ε_def}. If A = ∅, the run does nothing.

**Real-only adaptation.** θ_R = fit(D_ref ∪ D_real). This is always computed first.

**Residual deficiency / eligibility (v1.1, D4: recall).** I = {c ∈ A : LCB_α(1 − Recall_c(θ_R; D_sel)) > ε_def ∧ n_c ≥ n_min}
(the F1-based set is logged as a diagnostic only).
If I = ∅, the candidate is θ_R. Record the outcome as "real-only sufficient"; its frequency is a
primary result.

**E. Utility (region utility).** U(θ; 𝒟) = (1/|A|) Σ_{c∈A} F1_c(θ; 𝒟).

**Dose action.** θ(ρ⃗) = fit(D_ref ∪ D_real ∪ ⋃_c G_c.sample(m_c)), where
m_c = min(⌊ρ_c · n_c⌋, M_cap).

**D. Action space.**
𝒜_k = {STOP} ∪ {up(c) : c ∈ I_active, ρ_c has a next rung, the post-step φ ≤ φ_max}.
- up(c) moves ρ_c to the next ladder value.
- The generator G is fixed for each experimental condition. The controller chooses **class and
  dose only, never the generator**, so generator comparisons stay controlled.

**F. Marginal utility.** For a candidate step from θ_k to θ_k^{+c}:
ΔU_k(c) = U(θ_k^{+c}; D_sel) − U(θ_k; D_sel), and its lower bound is
L_k(c) = LCB_{α/K_max}(ΔU_k(c)).

**G. Intervention cost.**
- Utility cost per step: κ = η. Every step must pay for itself by at least η, measured at the
  lower confidence bound.
- Hard resource costs: M_cap and φ_max.
- Risk is not traded off against utility through a weight. It is a hard constraint (H).
- So the decision has two free knobs, η and α, and both are pre-registered.

**H. Stable-traffic degradation (two-part safety envelope).**
(v1.1, D2: every comparison below is against the fixed anchor θ_base = fit(D_ref), not the moving
incumbent.)
1. Historical capability: Δ_S(θ) = F1macro_{c∈C_S}(θ_base; S) − F1macro_{c∈C_S}(θ; S), where C_S
   is the set of pre-drift classes with support ≥ s_min in S.
2. Operational false-positive cost: Δ_B(θ) = FPR_benign(θ; 𝒟_B) − FPR_benign(θ_base; 𝒟_B), measured on
   S's benign rows **and** on the benign rows of the current drift labels (D_sel or D_gate).

A model is envelope-safe on (S, 𝒟) iff
UCB_α(Δ_S) ≤ ε_S ∧ UCB_α(Δ_B on S) ≤ ε_FPR ∧ UCB_α(Δ_B on current benign) ≤ ε_FPR.

**I. Stopping rule (greedy sequential, per run).** Start with k = 0, θ_0 := θ_R, ρ⃗ = 0. Then loop:
1. For every action in 𝒜_k other than STOP, fit θ_k^{+c} and compute L_k(c). Keep only the
   candidates that are envelope-safe on (S_sel, D_sel).
2. c* = argmax L_k(c) over the safe candidates.
3. **STOP** if: there are no safe candidates; or L_k(c*) ≤ η; or k = K_max; or no admissible
   action is left.
4. Otherwise accept: θ_{k+1} = θ_k^{+c*}, k ← k+1. A class whose step was unsafe or failed the
   test is removed from I_active.

The output is θ* = θ_k. If k = 0, θ* = θ_R.

**J.1 Promotion rule (on D_gate and S_gate only; these never influence a step).**
Candidates are θ₀, θ_R and θ*. Tests use α/2.
1. Promote θ* (only if k > 0) iff
   - point ΔU(θ*, θ_R; D_gate) > 0;
   - LCB(U(θ*) − U(θ_R); D_gate) ≥ −ε_ni;
   - LCB(U(θ*) − U(θ₀); D_gate) > 0;
   - θ* is envelope-safe on (S_gate, D_gate);
   - it passes `CandidateValidationGate`'s shape, NaN and sum-to-1 checks (reused).
2. Otherwise promote θ_R iff LCB(U(θ_R) − U(θ₀); D_gate) > 0 and θ_R is envelope-safe on the gate sets.
3. Otherwise keep θ₀.

The rejection reason is logged as one of: sanity, no_affected_region, utility_unmeasurable,
utility_no_gain, utility_inconclusive, envelope_unverifiable, envelope_violated,
envelope_inconclusive (v1.1, D3; the envelope_violated / envelope_inconclusive boundary is
redefined by v1.3 F1: violated only when the LCB exceeds ε), plus non-inferiority once θ* exists.

**J.2 Canary / rollback (prequential, on L_{t−1} before it is assigned to any partition).**
The promoted θ_new and the shadow θ_prev both score L_{t−1}. Roll back to θ_prev iff
UCB_α(U(θ_new) − U(θ_prev)) < 0 (significantly worse) or θ_new violates the benign-FPR envelope on
L_{t−1}'s benign rows. Rollbacks are counted and reported.

---

## 3. Module / API design (new package; existing modules unchanged so existing results stay reproducible)

```
proteus/intervention/
  __init__.py
  protocol.py     ScenarioConfig, build_partitions(seed, scenario) -> PartitionManifest;
                  StreamReplay -> iterates WindowBundle(t, E, U, L) with label delay;
                  ControllerView: the ONLY object the controller receives. It holds
                  D_ref/D_real/D_sel/D_gate/S_sel/S_gate and has no field for E_t,
                  S_report or future windows (leakage enforced by type)
  cache.py        one-time .npz cache of day-split arrays + group hashes (results/cache/,
                  gitignored), so the 16GB machine doesn't reload CSVs per run
  metrics.py      per_class_f1, region_utility, benign_fpr, stable_macro_f1,
                  paired_bootstrap(stat_fn, pred_a, pred_b, y, strata, R, rng) -> dist,
                  lcb/ucb, t_ci(values) (t-distribution, not z)
  learner.py      CandidateBuilder(ref, seed).build(D_real, D_syn) -> fitted RF  (pure, no mutation);
                  RealBuffer (FIFO, real rows only); reuses BoundedBufferClassifier's reservoir logic
  generators.py   class SyntheticGenerator(Protocol):
                      name: str; requires_gpu: bool
                      fit(X_c_fit: ndarray, c: int, rng) -> None
                      sample(n: int, rng) -> ndarray[float32]
                  RandomOversampler (duplicates = null generator), SMOTEGenerator (within-class,
                  k=min(5,n_c-1)), WGANGPGenerator (wraps WGANGPFull; pretrained pre-drift-only;
                  resume on X_c_fit only; asserts cuda), optional MMDPrefilter(base) wrapper
                  (permutation-calibrated threshold); shared postprocess: clip to per-feature
                  [min,max] of D_ref ∪ D_fit, non-negativity where real data is non-negative
  controller.py   InterventionController(generator, params).run(view, theta0) -> ControllerRun
                  (A, I, theta_R, step trace [c, rung, L_k, envelope stats, accepted], theta_star,
                  stop_reason)
  promotion.py    promote(view, theta0, theta_R, theta_star) -> Decision(model, reason, stats);
                  canary(theta_new, theta_prev, L_prev, A) -> keep|rollback
  conditions.py   FROZEN, REAL_ONLY, REAL_ONLY_ALL_LABELS(ref), FIXED_DOSE(gen, rho),
                  CONTROLLER(gen), ORACLE_DOSE(ref; selects rho on E, flagged non-deployable)
  experiment.py   run(scenario, budget, seeds, conditions) -> results/intervention_<scenario>_B<b>.json
                  (includes manifest hashes, SPEC version, param hash, git SHA, per-window logs)
proteus/gan_full.py   ADD (do not change existing behaviour): run_stage2_predrift(days, label_space)
                  writes checkpoints/gan_predrift_<scenario>/ with all 25 class slots
tests/test_intervention_protocol.py, _metrics.py, _generators.py, _controller.py, _promotion.py
```
Every new numeric module imports `proteus.config` first (thread-cap rule). `app.py`, `api/` and
`frontend/` are not touched.

---

## 4. Experiment protocol

### K. Minimal baseline set (all use the identical partitions, label budget and promotion rule)
| Condition | Purpose |
|---|---|
| FROZEN (θ₀) | Lower reference |
| REAL_ONLY | **The comparison that matters.** Real adaptation on the same fit rows, with the same gate |
| CTRL-ROS | The same controller with duplicate oversampling. Separates "new synthetic points" from "more weight on a class" |
| FIXED-SMOTE ρ∈{1,4} | Always-intervene at a fixed dose, through the same gate. Separates sequential dose search from simply adding synthetic data |
| **CTRL-SMOTE** | Proposed instance #1 |
| **CTRL-WGAN** | Proposed instance #2. Main study only, after the pre-drift-only retrain |
| *refs:* REAL_ONLY_ALL_LABELS, ORACLE_DOSE | An upper bound and a reproduction of the old regime. **Never claims** |

Static augmentation is dropped: it is already null and it uses the contaminated checkpoint.
MMD-prefilter variants are a later ablation, not part of the minimal set.

### Endpoints (always on E_t and S_report; never on anything the controller saw)
- **Primary:** recovery AUC = mean over post-drift windows t ∈ [t_d+1, t_d+H] of region F1 on the
  pooled E_t. The region is fixed after the fact as the classes that were drift-affected in that
  seed, with support ≥ s_min in pooled E.
- **Co-primary (safety):** stable macro-F1 drop and benign FPR increase on S_report, plus the
  envelope-violation rate among promoted models.
- **Secondary:** the share of runs ending "real-only sufficient", accepted dose per class, stop
  reasons, rollback count, present-class macro-F1, per-class F1, adaptation wall-clock.
  25-class macro-F1 appears only in an appendix.

### Statistics
- At least 5 seeds; 10 for the main study if wall-clock allows.
- Comparisons are paired per seed. Report the mean difference with a 95% **t**-CI (t₄ = 2.776 at
  n=5) and all per-seed values.
- The pilot has no headline claim; it is a go/no-go.

### L. Smallest falsifying pilot (scenario S1, 5 seeds, H = 10 post-drift windows + 4 pre-drift)
- **P0, room for intervention (FROZEN, REAL_ONLY and the REAL_ONLY_ALL_LABELS positive control;
  cheap; B ∈ {25, 100}).** Measure I across runs. **v1.2: the decision procedure is §L.1 below;
  the earlier "H1 is falsified if…" wording is superseded by it.**

<!-- P0-DECISION-RULES:BEGIN -->
#### L.1 P0 decision procedure (v1.2; normative, frozen before any P0 result exists)

Where code and this section disagree, this section is the specification. All counts below are the
ones of the approved review plan; no §1.5 threshold is touched, and none of these constants may be
changed after a P0 result exists (changing one bumps the SPEC version).

**Notation.** t_d = `n_pre_windows` is the first post-drift window; it only sees pre-drift labels
(label delay), so "post-drift windows" means t > t_d. D = the *drift classes*: classes with at least
one row in the drift pool and none in the pre-drift pool. At (budget b, seed s, window t): M_t = the
measurable classes, A_t = the affected region, I_t = the recall-based residual set (v1.1, D4),
n_c = the number of real fit rows of class c in the view. Budgets are nested: for a matched seed the
B=25 labelled rows are a prefix of the B=100 rows with identical roles and identical E_t.

**Scope.** Every check below is evaluated at EVERY budget of the grid, for every seed and every
condition, on the same manifests. Only R (checked to be budget-independent) and the final outcome
rule combine information across budgets.

**Repairable set R.** Seed s *repairs* a drift class c iff, at the final window of the
REAL_ONLY_ALL_LABELS positive control, c ∈ M, n_c ≥ n_min and c ∉ I. R = {c ∈ D : c is repaired in
at least 3 of 5 seeds}. Drift classes outside R are *unrepaired* and are reported separately with
their cause (residual deficiency, unmeasurable, or thin real support). A class outside R can never
generate a GO, however deficient it appears.

**Cells and budget status** (REAL_ONLY, post-drift windows only). A cell (b, s, t) is
*assessable* iff some c ∈ R ∩ M_t has n_c ≥ n_min. It is a *GO cell* iff I_t ∩ R ≠ ∅. Every GO cell
is assessable (c ∈ I implies c ∈ A ⊆ M and n_c ≥ n_min). Each budget receives exactly one status:
- **GO(b)** if at least 3 of 5 seeds have at least 2 GO cells;
- otherwise **NO_ROOM(b)** if at least 3 of 5 seeds have at least 2 assessable cells (the GO
  criterion was reachable and was not reached: informative negative evidence);
- otherwise **UNMEASURABLE(b)** (the GO criterion was unreachable: no evidence either way).
The three statuses are exhaustive and mutually exclusive. Insufficient support yields UNMEASURABLE,
never INVALID. The pooled share of unmeasurable cells is reported but is not a decision input.

**Validity (any failure ⇒ INVALID).**
- **V1, leakage and partition integrity.** Zero rows in any view array that come from E_t,
  S_report or S_cal, or from a group of theirs in the same pool; zero unlabelled rows (budget
  regime); zero rows from window ≥ t. Pre-pool partitions and the E/learning sides of the windows
  are pairwise group-disjoint within their pool; D_ref ⊆ TRAIN; no window row is reused; and the
  budgets are nested on every matched seed (labelled prefix, identical E_t). A group that occurs in
  both the pre-drift and the drift pool (an identical flow on different days) is legal and does NOT
  fail V1; it is reported (see diagnostics).
- **V3, integrity.** For FROZEN, at every post-drift (b, s, t) and every c ∈ D ∩ M_t: c ∈ A_t, with
  zero exceptions. FROZEN never predicts a class absent from D_ref, so an exception is a pipeline
  defect. A GO cell that is not assessable is likewise an integrity violation. The number of cells
  checked is reported (the check is vacuous where nothing is measurable).
- **V4, repairability of the positive control.** R ≠ ∅, and R is identical at every budget. If R is
  empty, abundant labels do not repair any drift class and the learner or reservoir is fixed first.

**Diagnostics (mandatory, reported before the outcome, never gate it).**
- **V2, null region.** At each budget, A_FROZEN at the last pre-drift window is empty in at least 4
  of 5 seeds. A failed V2 does not change the P0 outcome; it blocks P1 and any later claim until a
  spec revision defines how pre-existing (non-drift) deficiency enters A, U and I.
- **Cross-pool duplicate reporting.** Counts, per learning buffer (D_real, D_sel, D_gate), of rows
  whose group occurs in S_report, S_gate, S_sel, S_cal or D_ref, split by pool of the row (training
  rows exactly duplicated in stable evaluation rows are the D_real counts), plus the number of
  groups and rows that occur in both temporal pools.
- **Conflicting-label reporting.** The number of groups (feature vectors) that carry more than one
  label anywhere in the corpus, split into within-pool and across-pool conflicts, and for every
  drift class the share of its final-window D_sel rows and of its pooled E rows whose group
  carries another label. A class that generates a GO and has either share ≥ ε_def (§1.5) is flagged
  "possibly ambiguity-driven". The flag never gates the outcome, but contradictory vectors can be
  intrinsically unrepairable, so a GO that carries the flag must be reported with that
  qualification and requires interpretation before it is cited.
- **Descriptive.** Unmeasurable-cell fraction, support counts, the D3 rejection taxonomy, recovery
  on E_t, the S_report effect against θ_base, buffer evictions, wall-clock time.

**Outcome (exclusive, exhaustive, applied in this order; only a run whose scenario, budgets,
seeds, params digest and criteria digest equal the preregistered ones receives an outcome, any other
run is reported as "not preregistered" with no outcome).**
1. **INVALID** if any validity check fails. The invalid run makes no H1 statement; the named cause
   is fixed and all of P0 is rerun with the same seeds.
2. **GO** if GO(b) holds for some b. Proceed to P1 at the smallest GO budget.
3. **NO_GO_NO_ROOM** if no budget is GO and NO_ROOM(b) holds for some b. The conclusion is stated
   for the assessed budgets only, mechanically, e.g. "NO_ROOM at B=100; B=25 unmeasurable"; an
   UNMEASURABLE budget is not evidence either way. Run P0 on S2 under these same rules; if S2 is
   also NO_GO_NO_ROOM, stop: "real-only adaptation suffices at the assessed budgets".
4. **INCONCLUSIVE_UNMEASURABLE** if every budget is UNMEASURABLE. Rerun P0 adding B = 400 (same
   seeds, nested) and re-evaluate over {25, 100, 400}; if it is still INCONCLUSIVE_UNMEASURABLE,
   S1 is declared not assessable under the frozen protocol and P0 moves to S2.
There is no other outcome label (in particular no "mixed" outcome). s_min, n_min and ε are never
relaxed to obtain a different status.
<!-- P0-DECISION-RULES:END -->

- **P1, intervention (only if P0 passes; the budget is the smallest one that passed P0, chosen
  from REAL_ONLY data only).** Conditions: FROZEN, REAL_ONLY, CTRL-ROS, FIXED-SMOTE ρ∈{1,4},
  CTRL-SMOTE.
  - **H2:** the paired recovery-AUC difference CTRL-SMOTE − REAL_ONLY has a 95% CI lower bound > 0.
  - **H3:** CTRL-SMOTE − CTRL-ROS has a CI lower bound > 0.
  - **H4 (safety):** no promoted CTRL-SMOTE model breaks the S_report envelope in any seed, and the
    envelope-violation rate of raw FIXED-SMOTE ρ=4 candidates is reported.
  - **H5:** CTRL-SMOTE ≥ the best FIXED-SMOTE within ε_ni.
- Cost estimate: about 31 RF fits (~3 s each) per controller run × 10 windows ≈ 15 min per seed per
  controller condition, so roughly 3 h for P1. GAN work does not start until P1 passes.

---

## 5. Implementation order (commit after each passes its own check; one-line messages, no attribution)

0. Copy this spec to `docs/INTERVENTION_SPEC.md` (SPEC v1.0) and log the reframing in `CHANGELOG.md`.
1. `cache.py` + `protocol.py` + `test_intervention_protocol.py`. Tests: group-disjointness across
   all partitions; non-replacing windows; label delay; `ControllerView` has no E/S_report access;
   manifest is reproducible from the seed.
2. `metrics.py` + tests: bootstrap against known toy distributions; the t-CI.
3. `learner.py` + `promotion.py` + REAL_ONLY/FROZEN conditions. Sanity check: REAL_ONLY_ALL_LABELS
   should reproduce the old qualitative Stage-7 pattern under the new protocol.
4. **Run P0.** Append to `METRICS_HISTORY.md`. Go/no-go decision point; if H1 is falsified, stop
   and report.
5. `generators.py` (ROS, SMOTE) + tests: class purity, determinism, clipping, never fit on
   sel/gate/E.
6. `controller.py` + tests, with injected toy utility functions to check each stop condition, the
   α/K_max adjustment, envelope exclusion and argmax selection.
7. Canary wired into `experiment.py`. **Run P1.** Append metrics, then a second go/no-go.
8. `gan_full.run_stage2_predrift` (GPU, assert cuda) + `WGANGPGenerator` + CTRL-WGAN.
9. Main study: S1+S2, B ∈ {25, 100, 400}, at least 5 seeds. Update `ARCHITECTURE.md`,
   `STATUS.md` and the paper evidence map.
10. (Infra, optional) plug `promotion.promote` into `drift_daemon.CandidateValidationGate` as an
    alternative gate. No research claims follow from this.

## 6. Anti-leakage rules (each enforced by a test or an assertion)
1. E_t, S_report and future windows are never reachable from `ControllerView`, and their indices
   are never passed to the controller.
2. Partitions are group-disjoint by feature hash. Windows are non-replacing.
3. Prequential order: score W_t with the model fitted on labels from ≤ t−2 windows (because of
   the label delay) before any update.
4. Step decisions use D_sel and S_sel only. Promotion uses D_gate and S_gate only. Canary uses
   L_{t−1} before it is assigned. A row never changes partition.
5. (v1.1, D5) Generators are fit only on D_ref plus the D_fit rows of the target class. This
   includes WGAN-GP pretraining and its normalisation statistics: no TRAIN-wide pretraining.
6. The KS reference is S_cal, never training rows.
7. Every threshold in §1.5 is frozen before P0. Changing one bumps the SPEC version and reruns
   every affected condition. Nothing is tuned on E or S_report. ORACLE_DOSE is labelled
   non-deployable.
8. One seed controls every RNG. Each result JSON stores the manifest hash, SPEC version, parameter
   hash and git SHA.
9. No result produced by the legacy `closed_loop_full`/`evaluate_full` path or the old
   `checkpoints/gan_full` may be cited as evidence for synthetic intervention.

## 7. Failure criteria (any one is a reportable outcome, never a reason to retune)
- **F1 (no room):** H1 falsified in both S1 and S2 → the conclusion is that real-only adaptation
  is sufficient.
- **F2 (no utility):** the H2 CI lower bound ≤ 0 → synthetic intervention gives no measurable
  recovery beyond real labels.
- **F3 (not synthetic):** the H3 CI lower bound ≤ 0 → any gain is a reweighting effect; plain
  oversampling does as well.
- **F4 (unsafe):** any promoted controller model breaks the S_report envelope, or the rollback rate
  is > 20% of promotions → the safety mechanism has failed.
- **F5 (controller adds nothing):** CTRL is worse than the best FIXED dose by more than ε_ni → the
  stopping rule is not doing useful work.
- **F6 (unmeasurable):** in more than 80% of runs, A ≠ ∅ but I ∩ M = ∅ because of support. This is
  the label-scarcity tension: the regime where synthetic data might help is the regime where its
  benefit can't be measured. Report it as a core finding.
- **F7 (generator):** CTRL-WGAN is not better than CTRL-SMOTE (CI lower bound ≤ 0) → the WGAN-GP's
  added cost isn't justified. Report SMOTE as the recommended generator.

## M/N. Component roles and generator interface (decisions)
- **Research-critical:** the protocol and partitioning; real-only bounded adaptation; generators
  (ROS, SMOTE, WGAN-GP); controller; bootstrap metrics; promotion and canary rules; KS trigger
  (secondary, since the pilot uses the oracle trigger).
- **Infrastructure-only:** release manager, model manager hot-swap, drift daemon threading,
  FastAPI, Next.js, Streamlit demo, Ryu/Mininet, feature mapper, Docker.
- **MMD:** demoted from decision-maker to an optional pre-filter ablation. Measured marginal
  utility is the decision signal.
- **Generators:** every generator implements the same `fit` / `sample` protocol, sees only
  target-class D_fit rows, gets the same post-processing, and is fixed per condition. The
  controller is generator-agnostic. ROS is the null generator, SMOTE the cheap generator, and
  WGAN-GP the learned one. WGAN-GP (v1.1, D5) is pretrained on D_ref only, with all 25 one-hot
  slots reserved and normalisation statistics from D_ref, and fits a new class by resuming on
  that class's few D_fit rows.

## Verification (of the implementation, once approved)
- `.venv/bin/python -m pytest tests/test_intervention_*.py -q`: all leakage, metric and controller
  tests pass, and the existing 53 tests stay green.
- `python -c "import torch; assert torch.cuda.is_available()"` before step 8.
- P0 and P1 JSONs exist under `results/` with manifest hash and git SHA, and each run gets a
  `METRICS_HISTORY.md` entry that points to the artifact.
- A spot audit script recomputes, from the manifest, that no E or S_report group hash appears in
  any fit, sel or gate set or in generator inputs.
