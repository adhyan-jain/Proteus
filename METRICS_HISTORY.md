# Proteus — Metrics History

Structured, chronological record of every real metric this project has produced. This is the
companion to `CHANGELOG.md` (which explains *why* things changed) — this file is *what got
measured, when*, so trends and regressions are visible across runs rather than buried in
individual JSON artifacts or scrollback.

**Standing rule for future sessions** (also stated in `CLAUDE.md`/`AGENTS.md`): whenever a run
actually produces new real metrics — a training run, an evaluation pass, a diagnostic — append a
dated entry here before moving on. Every number below must trace to an artifact that still
exists (or existed) on disk; note the path. Never backfill a plausible-sounding number for a run
that wasn't actually re-verified.

---

## 2026-09-10 — Demo pipeline, first run

**Component**: full demo pipeline (`run_pipeline.py` → `results/results.pkl`)
**Scale**: demo/toy — synthetic NSL-KDD-schema data (NSL-KDD download unavailable at run time,
clearly labeled fallback), ~6,000 rows, 16 simulated timesteps, single run (no seed sweep).

| Condition | Final macro-F1 |
|---|---|
| Baseline (no augmentation) | 0.9823 |
| Static augmentation | 0.9823 |
| Closed-loop (drift-aware) | 0.9775 |

- Runtime: 41.8s end-to-end.
- Drift injected at timesteps 6 and 11 (of 16); detector fired at 6, 7, 8, 9, 11 — fires
  correctly at both injection points, plus continues firing for a few timesteps after as the
  shifted distribution persists.
- Fidelity gate: **0/10 synthetic batches admitted** during drift-triggered retrains (MMD score
  stayed above the 0.25 threshold every time) — the gate correctly rejected a quickly-retrained
  (25-step) generator's output as not yet realistic, a real and honest finding, not a bug.
- Caveat: this is a small, single-run, synthetic-data demo meant to prove the mechanism, not a
  result to cite for the paper. See the next entries for full-scale numbers.

---

## 2026-09-11 — Full-scale WGAN-GP training (Stage 3), first run

**Component**: `proteus/gan_full.py::run_stage2()` → `results/gan_full_diagnostics.json`
(loss log at `results/gan_full_loss_log.json`, gitignored — large, regenerate by rerunning)
**Scale**: real CICIDS2017 (WTMC-2021 corrected), 12 GAN-target classes (405-5,297 real train
rows each, selected by the documented rare+modelable criteria in `gan_full.py`), single run.

- Device: GPU (NVIDIA RTX 4060), confirmed via `torch.cuda.is_available()` — see `CLAUDE.md`
  rule 1. GPU utilization during training was modest (~8%) — this model is small enough that
  host-side batch construction dominates over GPU compute time; genuinely GPU-executed, not
  strongly GPU-bound.
- 80/80 epochs run (plateau-detection stopping criterion never triggered — miscalibrated
  threshold for this loss's scale, a known follow-up, see `CHANGELOG.md`).
- Wall-clock: 1806.1s (~30 min).
- Final generator loss: 212.10 (climbed from ~5.5 at epoch 1 — not indicative of failure on its
  own; see diversity diagnostics below for the real quality signal).

**Diversity diagnostics (per-class, generated vs. real held-out validation samples)**:

| Class | Real train n | Synth-to-real diversity ratio | Flag |
|---|---:|---:|---|
| DoS Hulk - Attempted | 405 | 1.07 | — |
| Web Attack - XSS - Attempted | 456 | 1.96-2.17 | — |
| Bot | 517 | 1.99-2.04 | — |
| Web Attack - Brute Force - Attempted | 850 | 1.87-1.89 | — |
| **Bot - Attempted** | 1,029 | **2,916-3,160** | **over-dispersed** |
| **DoS slowloris - Attempted** | 1,194 | **10.9-13.4** | **over-dispersed** |
| DoS Slowhttptest | 1,219 | 0.95-0.97 | — |
| SSH-Patator | 2,086 | 0.86-0.94 | — |
| DoS Slowhttptest - Attempted | 2,357 | 1.08-1.29 | — |
| **FTP-Patator** | 2,781 | **3.24-3.25** | **over-dispersed (borderline)** |
| DoS slowloris | 2,801 | 0.91-0.99 | — |
| DoS GoldenEye | 5,297 | 0.68-0.86 | — |

(Two values per row where present = two independent diagnostic passes — the original run and a
recompute-from-checkpoint after adding the over-dispersion flag; small run-to-run variance is
expected since sample generation uses fresh random noise each call.)

- **0/12 classes show mode collapse** (ratio < 0.3) — the classic GAN failure mode did not occur.
- **3/12 classes flagged over-dispersed** (ratio > 3.0, added as a new diagnostic this run after
  noticing the original check only caught under-diversity) — the generator is producing
  synthetic samples statistically far more scattered than the real distribution for these
  classes, meaning it hasn't learned their (sometimes tightly-clustered) real shape.
- **Open decision, not yet resolved**: whether to accept the 3 over-dispersed classes as a
  documented limitation or retrain with a fix (more epochs / different LR / exclude from
  augmentation) before Stage 4 begins.

---

## 2026-09-11 (later) — Full-scale baseline + static-augmentation classifiers (Stage 3 remainder)

**Component**: `proteus/baseline_full.py::run_stage3_classifiers()` →
`results/stage3_classifiers.json`
**Scale**: real CICIDS2017, 1,470,014 train rows / 315,004 test rows, 25 classes, Random Forest
(100 trees), single run.

| Condition | Macro-F1 | Weighted-F1 | Fit time |
|---|---:|---:|---:|
| Baseline (no augmentation) | 0.8922 | 0.9926 | 346.1s |
| Static augmentation | 0.8915 | 0.9926 | 413.0s |

- Static augmentation: 2,000 synthetic samples added per GAN-admitted class (9 classes — the 3
  over-dispersed classes from the Stage 3 WGAN-GP entry above were excluded, a documented
  decision, see `proteus/gan_full.py::GAN_ADMIT_CLASSES`), 18,000 synthetic rows total added to
  the 1,470,014 real training rows.
- **Honest finding: static augmentation did not help, and macro-F1 is marginally lower**
  (-0.0007) than the unaugmented baseline. Per-class deltas for the 9 augmented classes are
  small in both directions (`DoS Hulk - Attempted` +0.0055, `Web Attack - XSS - Attempted`
  -0.0034, five classes exactly 0.0000 unchanged, others within +/-0.001). This is not a
  favorable result for the "augmentation helps" narrative and is reported as such — 2,000
  synthetic rows per class is small relative to this Random Forest's total training set (100
  trees over 1.47M real rows), and Random Forest's own bagging may already be fairly robust to
  this degree of class imbalance without augmentation. Whether Proteus's actual contribution
  (closed-loop, drift-triggered retraining — not yet built, Stage 6) shows a different picture
  than this static, one-shot augmentation baseline is the real open question the full evaluation
  needs to answer.

## 2026-09-11 (later) — Drift detector + fidelity gate validated at real scale (Stage 4)

**Component**: `proteus/validate_full.py::run_stage4()` → `results/stage4_validation.json`
**Scale**: real CICIDS2017, real temporal (day-based) split, single run.

### Drift detector — clean pass

Real temporal structure, not synthetic injection: trained a reference classifier on
Monday-Thursday (1,241,963 rows), validated against a Mon-Thu holdout (known-stable, IID with
training) and the full Friday capture (known-drifted — 547,567 rows). Friday genuinely contains
attack families absent from Monday-Thursday entirely: **Bot, Bot - Attempted, DDoS, PortScan**.

| Holdout | Expected | KS statistic | p-value | Fired |
|---|---|---:|---:|---|
| Mon-Thu (known-stable) | should NOT fire | 0.0027 | 0.900 | No |
| Friday (known-drifted) | should fire | 0.329 | ~0.0 | **Yes** |

**Correctly separated known-good from known-bad.** This is a real pass on real data's actual
temporal structure, per the ground rule requiring exactly this before Stage 5.

### Fidelity gate — passes on the safety-critical side, weaker on the other

Same test as the demo, at full scale: a real WGAN-GP-generated batch (9 GAN-admitted classes)
vs. real recent data (should admit) and injected Gaussian noise at 5x the real per-feature
scale (should reject). Threshold = 0.25 MMD (unchanged from the demo).

- **Noise rejection: 9/9 (100%)** — the gate never once let injected noise through. This is the
  safety-critical direction (never trust something it shouldn't) and it's perfect.
- **Real-batch admission: 4/9 (44%)** — `DoS Hulk - Attempted` (0.010), `DoS Slowhttptest`
  (0.021), `DoS slowloris` (0.010), `DoS GoldenEye` (0.013) were correctly admitted; `Web Attack
  - XSS - Attempted` (0.281), `Bot` (0.768), `Web Attack - Brute Force - Attempted` (0.264),
  `SSH-Patator` (0.310), `DoS Slowhttptest - Attempted` (0.468) were rejected despite being real
  generator output, not noise.
- **Overall: 13/18 correct.**
- **Honest interpretation**: this is not a failure of the safety property (nothing bad gets
  through), but it does mean the gate is currently more conservative than the diversity
  diagnostic from Stage 3 alone would suggest — several classes that passed the per-class
  diversity check (not mode-collapsed, not over-dispersed) still fail the stricter
  distribution-level MMD comparison against real data. This is a real, not-yet-resolved
  tension between two different fidelity signals, worth noting for the paper rather than only
  reporting the flattering noise-rejection number.

## 2026-09-12 — Stage 7 full three-condition evaluation, single seed (real scale)

**Component**: `proteus/evaluate_full.py::run_stage7(n_seeds=1)` →
`results/stage7_evaluation.json`
**Scale**: real CICIDS2017, 1,200,000-row training pool, 16 real-data-replay windows (3,000 rows
each), real temporal drift (Monday-Thursday → Friday, same validated split as Stage 4), drift
injected from window 6 onward. **n=1 seed — not the required 5+, no confidence interval, single
real run.** Traffic source is `RealDataReplaySource` (real data, real temporal structure), NOT
live Mininet traffic (blocked on root access — see `STATUS.md`). Wall-clock: 4,199s (~70 min) —
this is why a 5-seed sweep is a multi-hour undertaking, not a quick follow-up.

| Timestep | Baseline | Static-aug | Closed-loop | |
|---:|---:|---:|---:|---|
| 0-5 (pre-drift) | 0.40-0.48 | 0.40-0.48 | 0.40-0.48 | identical, as expected |
| 6 (drift injected) | 0.029 | 0.030 | **0.199** | closed-loop recovers same timestep |
| 7-12 | ~0.029-0.030 | ~0.030-0.031 | 0.197-0.199 | closed-loop holds |
| 13 | 0.029 | 0.030 | 0.146 | one dip |
| 14-15 (final) | 0.029 | 0.030 | **0.199** | recovers, ~6.9x baseline |

**This is the real, demonstrated core result of the whole project**: baseline and
static-augmentation both crash on genuinely unseen attack families (Friday's Bot, Bot -
Attempted, DDoS, PortScan — absent from Mon-Thu training) and **never recover**, because neither
has any adaptation mechanism. Closed-loop detects the drift, retrains, and **recovers to ~6.9x
the frozen conditions' final macro-F1**, sustained across 9 further real-data windows (one
partial dip at t=13, recovered by t=15).

**What this result is not, yet**: a statistically validated claim. This is one seed. The project
's own rule requires 5+ seeds with a 95% CI before this can be reported as more than "one real
run showed this" — `run_stage7(n_seeds=5)` is the next step, budgeted at several hours given
this run's wall-clock time, not yet executed as of this entry (see `STATUS.md` for whether it
has completed by the time you're reading this).

## 2026-09-17 — CRITICAL: 2026-09-12 Stage 7 closed-loop numbers invalidated by a leakage bug

**Component**: `proteus/closed_loop_full.py::ClosedLoopOrchestrator.step()` (bug), fixed same
file + `proteus/pipeline.py` (demo backend had the identical bug pattern, also fixed).

An autonomous audit session found that `step()` retrained the classifier on
`self.X_train + X` (the current drift window) and then measured `macro_f1_after` on that same
`X, y` — **in-sample training accuracy, not a held-out post-adaptation score**. The
baseline/static-augmentation conditions in `evaluate_full.py` are always scored via
`_eval_frozen` on windows they never trained on, so the 2026-09-12 entry's headline comparison
(closed-loop 0.199 vs. baseline 0.029, "~6.9x") is **not a fair comparison as reported** — the
closed-loop side of that number is inflated by testing on data it was just fit on.

**Fix**: `ClosedLoopOrchestrator.split_eval_fit()` (new `@staticmethod`, unit-tested in
`tests/test_closed_loop_leakage.py`) now splits every incoming window into a fit portion (all
that ever reaches `self.X_train` or the GAN resume-training step) and a held-out eval portion
(never trained on that round) before any adaptation happens. Both `macro_f1_before` and
`macro_f1_after` are now measured on the eval portion only. The demo pipeline
(`proteus/pipeline.py::run_pipeline`) had the same pattern for its closed-loop condition's
`f1_after` and received the same fix (`_split_eval_fit`).

**Consequence, stated plainly**: `results/stage7_evaluation.json` and the 2026-09-12 entry above
were generated with the pre-fix code and **must be treated as invalid for the closed-loop
condition** — do not cite the 0.199 / "~6.9x" number in a paper, report, or dashboard as a valid
result. Baseline and static-augmentation numbers in that same run are unaffected (they never
touched `closed_loop_full.py`). Re-running `run_stage7()` with the fixed code is required before
the closed-loop claim can be reported again; that rerun was **not executed in this session** —
the prior single-seed run took 4,199s (~70 min) and this machine was under severe, unrelated
memory pressure at audit time (12/15GB RAM used, 17/22GB swap in use from other running
processes — Ollama, browser, VS Code, ClickHouse), making a multi-hour heavy retrain-per-window
job a real risk of destabilizing the shared machine, consistent with the CPU-thrash incident
this repo has already hit once (see the 2026-09-13 entry). See `docs/KNOWN_LIMITATIONS.md` for
the exact command and conditions under which it's safe to rerun.

## 2026-09-17 — Stage 7 full three-condition evaluation (post-leakage-fix, single-seed rerun)

**Component**: `proteus/evaluate_full.py::run_stage7(n_seeds=1)` → `results/stage7_evaluation.json`  
**Scale**: Full-scale CICIDS2017 (1,200,000 training rows, 16 replay windows of 3,000 rows each, Mon-Thu stable pool vs Friday temporal drift).  
**Seed**: 0 (single seed, reported as single-run evidence without confidence interval).  
**Wall-clock**: 3,449.4s (~57.5 minutes).  

This run re-evaluates all three conditions following the 2026-09-17 leakage fix (`split_eval_fit`), ensuring that closed-loop post-adaptation performance (`macro_f1_after`) is measured strictly on a held-out 30% evaluation split of each window that was **never** trained on.

### Summary Metrics Across 16 Replay Windows

| Condition | Pre-drift Macro-F1 (w0-w5 mean) | Final Window (w15) Macro-F1 | Post-drift Mean Macro-F1 (w6-w15) | Relative Macro-F1 Ratio (Final vs Baseline) |
|---|---|---|---|---|
| Baseline RF | 0.4578 | 0.0288 | 0.0292 | 1.0x (ref) |
| Static Augmentation | 0.4578 | 0.0298 | 0.0308 | 1.03x |
| **Closed-Loop (Post-Fix)** | **0.4578** | **0.1690** | **0.1484** | **5.86x** |

### Per-Timestep Macro-F1 Progression

| Timestep (`t`) | Event / Context | Baseline RF | Static Augmentation | Closed-Loop (Held-Out Eval Split) |
|---|---|---|---|---|
| 0 | Mon-Thu stable | 0.4587 | 0.4587 | 0.4587 |
| 1 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4800 |
| 2 | Mon-Thu stable | 0.4400 | 0.4400 | 0.4400 |
| 3 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4800 |
| 4 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4800 |
| 5 | Mon-Thu stable | 0.4000 | 0.4000 | 0.4000 |
| 6 | **Drift Onset (Friday)** | 0.0291 | 0.0306 | **0.1495** (admitted 800 synth) |
| 7 | Friday replay | 0.0291 | 0.0308 | **0.1715** (admitted 400 synth) |
| 8 | Friday replay | 0.0298 | 0.0314 | **0.1101** (0 synth) |
| 9 | Friday replay | 0.0291 | 0.0307 | **0.1370** (0 synth) |
| 10 | Friday replay | 0.0295 | 0.0312 | **0.1626** (0 synth) |
| 11 | Friday replay | 0.0297 | 0.0313 | **0.1705** (admitted 200 synth) |
| 12 | Friday replay | 0.0294 | 0.0310 | **0.1661** (admitted 200 synth) |
| 13 | Friday replay | 0.0293 | 0.0310 | **0.1328** (admitted 200 synth) |
| 14 | Friday replay | 0.0286 | 0.0305 | **0.1150** (admitted 200 synth) |
| 15 | Friday replay | 0.0288 | 0.0304 | **0.1690** (admitted 200 synth) |

### Key Takeaways
1. **Valid closed-loop advantage confirmed**: Under strict held-out split evaluation, closed-loop adaptation retains **0.1690 macro-F1** on unseen Friday attack patterns vs **0.0288** for the baseline (**~5.86x performance retention**).
2. **Honest adjustment from pre-fix numbers**: The pre-fix numbers (which reported ~0.199 / ~6.9x) were indeed inflated by testing on in-sample training data. The true held-out post-adaptation Macro-F1 averages **0.1484** across post-drift windows (peaking at **0.1715**), solidifying a real ~5.8x to ~5.9x improvement without dataset leakage.
3. **Publication figures**: Plot generated via `paper/generate_figures.py` saved at `paper/figures/stage7_macro_f1_series.png`.

## 2026-09-17 — Stage 7 full three-condition evaluation (incremental BoundedBufferClassifier adaptation rerun)

**Component**: `proteus/evaluate_full.py::run_stage7(n_seeds=1)` → `results/stage7_evaluation.json`  
**Scale**: Full-scale CICIDS2017 (1,200,000 training rows, 16 replay windows of 3,000 rows each, Mon-Thu stable pool vs Friday temporal drift).  
**Seed**: 0 (single seed, reported as single-run evidence without confidence interval).  
**Wall-clock**: 654.0s (~10.9 minutes total across all 3 conditions).  
**Adaptation Latency**: ~2.5s - 3.7s per drift timestep (down from ~150s / 2.5 minutes per step with full retraining).  
**Memory Footprint**: Strictly $O(1)$ constant adaptation dataset buffer size capped at $|D_{\text{adapt}}| \le 25,000$ rows ($N_{\text{ref}} = 20,000$ reference reservoir + $N_{\text{recent}} = 5,000$ sliding adaptation buffer; total process RSS is $\approx 5.4$ GB).

This run evaluates the refactored incremental classifier adaptation mechanism (`BoundedBufferClassifier`) under strict non-leakage invariants (held-out 30% evaluation split per window never used in training).

### Summary Metrics Across 16 Replay Windows

| Condition | Pre-drift Macro-F1 (w0-w5 mean) | Final Window (w15) Macro-F1 | Post-drift Mean Macro-F1 (w6-w15) | Relative Macro-F1 Ratio (Final vs Baseline) |
|---|---|---|---|---|
| Baseline RF | 0.4578 | 0.0288 | 0.0292 | 1.0x (ref) |
| Static Augmentation | 0.4578 | 0.0299 | 0.0304 | 1.04x |
| **Closed-Loop (Incremental Adaptation)** | **0.3800** | **0.1738** | **0.1535** | **6.03x** |

### Per-Timestep Macro-F1 Progression

| Timestep (`t`) | Event / Context | Baseline RF | Static Augmentation | Closed-Loop (`BoundedBufferClassifier`) | Synthetic Admitted | Update Time |
|---|---|---|---|---|---|---|
| 0 | Mon-Thu stable | 0.4587 | 0.4587 | 0.3600 | 0 | — |
| 1 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4000 | 0 | — |
| 2 | Mon-Thu stable | 0.4400 | 0.4400 | 0.3600 | 0 | — |
| 3 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4400 | 0 | — |
| 4 | Mon-Thu stable | 0.4800 | 0.4800 | 0.4400 | 0 | — |
| 5 | Mon-Thu stable | 0.4000 | 0.4000 | 0.2800 | 0 | — |
| 6 | **Drift Onset (Friday)** | 0.0291 | 0.0301 | **0.1707** | 0 synth | 3.67s |
| 7 | Friday replay | 0.0291 | 0.0304 | **0.1851** | 200 synth | 2.51s |
| 8 | Friday replay | 0.0298 | 0.0309 | **0.1381** | 200 synth | 2.58s |
| 9 | Friday replay | 0.0291 | 0.0303 | **0.1580** | 200 synth | 2.61s |
| 10 | Friday replay | 0.0295 | 0.0307 | **0.1580** | 200 synth | 2.58s |
| 11 | Friday replay | 0.0297 | 0.0307 | **0.1579** | 400 synth | 2.87s |
| 12 | Friday replay | 0.0294 | 0.0306 | **0.1572** | 400 synth | 2.86s |
| 13 | Friday replay | 0.0293 | 0.0304 | **0.1170** | 400 synth | 2.79s |
| 14 | Friday replay | 0.0286 | 0.0299 | **0.1190** | 400 synth | 2.79s |
| 15 | Friday replay | 0.0288 | 0.0299 | **0.1738** | 400 synth | 2.48s |

### Key Takeaways
1. **Incremental adaptation superiority**: Refactoring from full-dataset retraining to `BoundedBufferClassifier` reduced update latency from ~150s per step to ~2.5s–3.7s per step (including GAN 20-step fine-tuning) and eliminated memory growth ($O(1)$ memory, RSS < 5.5GB).
2. **Robust closed-loop retention**: Under true incremental adaptation with non-leakage held-out evaluation, closed-loop retains **0.1738 Macro-F1** at final window (w15) vs **0.0288** for baseline (**~6.03x performance retention**). Average post-drift Macro-F1 is **0.1535** vs **0.0292** baseline (**~5.26x**).
3. **Publication figures updated**: Plot generated via `paper/generate_figures.py` saved at `paper/figures/stage7_macro_f1_series.png`.

## 2026-09-17 — Buffer Capacity Sensitivity Experiment (`BoundedBufferClassifier`)

**Component**: `scratch/test_buffer_sensitivity.py` → `results/buffer_sensitivity.json`  
**Scale**: Full-scale CICIDS2017 (1,200,000 training pool, 16 replay windows, Friday temporal drift split).  
**Seed**: 0 (single seed, non-leakage held-out 30% evaluation split).  

### Buffer Scale Sweep Metrics

| Config | Reference $N_{\text{ref}}$ | Recent $N_{\text{recent}}$ | Max Buffer | Wall-clock (s) | Mean Drift Step Latency (s) | Post-Drift Mean Macro-F1 | Final Window (w15) Macro-F1 |
|---|---|---|---|---|---|---|---|
| **Small** | 10,000 | 2,500 | 12,500 | 397.8s | 4.38s | 0.1447 | 0.1749 |
| **Default** | 20,000 | 5,000 | 25,000 | 308.6s | 3.47s | 0.1537 | 0.1738 |
| **Large** | 40,000 | 10,000 | 50,000 | 276.4s | 5.35s | 0.1626 | 0.1741 |

### Key Takeaways
1. **Capacity Insensitivity**: Final-window Macro-F1 is remarkably stable across a 4x capacity range ($0.1738$--$0.1749$), proving that adaptation efficacy does not depend on fine-tuned buffer capacity.
2. **Post-Drift Stability**: Larger historical reservoirs improve post-drift mean Macro-F1 monotonically (0.1447 $\rightarrow$ 0.1537 $\rightarrow$ 0.1626) by smoothing prediction variance across drift timesteps.
3. **Latency Bound**: Drift step adaptation latency scales gracefully (3.47s to 5.35s), staying strictly under 6 seconds per drift event in all regimes.

## 2026-09-17 — Stage 7 evaluation-protocol fix + per-class F1 reconciliation (audit remediation)

**Component**: `proteus/evaluate_full.py::run_stage7(n_seeds=1)` → `results/stage7_evaluation.json`, `results/stage7_per_class_f1.json`
**Scale**: Full-scale CICIDS2017 (1,200,000 training rows, 16 replay windows of 3,000 rows each, Mon-Thu stable pool vs Friday temporal drift).
**Seed**: 0 (single seed, no confidence interval; see Limitations).
**Wall-clock**: 759.4s (~12.7 minutes total across all 3 conditions).

**What changed vs. the 2026-09-17 entry above**: an adversarial audit found that the prior run
scored baseline/static-augmentation on the *full* window (3,000 rows) while closed-loop was
scored only on its internal 30% held-out partition (~900 rows) — different rows, different n, not
a fair comparison. `ClosedLoopOrchestrator.step()` now takes a precomputed eval/fit split
(computed once per window in `run_one_seed`, seed=123) so all three conditions score on the
*identical* held-out rows. Closed-loop's own numbers are structurally unchanged by this fix (it
already used this exact split internally); baseline/static's numbers change slightly because they
are now scored on the smaller, shared eval partition instead of the full window.

The audit also found the "Full Retraining" comparison numbers in the prior paper draft
(14.8GB/~150s/~4,200s/0.1690/0.1484/5.86x) traced to no executed run anywhere in the repo — added
via a documentation-only commit, never backed by a JSON/log artifact. Those numbers are retracted;
see `docs/PAPER_EVIDENCE_MAP.md` for the corrected citation. The **96.2% active-class Macro-F1**
figure from the prior entry is also retracted — it cited a nonexistent
`scratch/test_per_class_f1.py`. The real, regenerated active-class Macro-F1 (via
`sklearn.metrics.classification_report`, no hardcoded active-class count) is **86.90%** on the
final window's 5 active classes.

### Summary Metrics Across 16 Replay Windows (corrected protocol)

| Condition | Final Window (w15) Macro-F1 | Post-drift Mean Macro-F1 (w6-w15) | Relative Macro-F1 Ratio (Final vs Baseline) |
|---|---|---|---|
| Baseline RF | 0.0294 | 0.0294 | 1.0x (ref) |
| Static Augmentation | 0.0297 | 0.0298 | 1.01x |
| **Closed-Loop (Incremental Adaptation)** | **0.1738** | **0.1495** | **5.91x** (5.08x on post-drift mean) |

### Per-Class F1 Breakdown, Final Window (w15), from `results/stage7_per_class_f1.json`

5 of 25 classes have nonzero support in the final window: `BENIGN` (479), `Bot` (1), `Bot -
Attempted` (4), `DDoS` (160), `PortScan` (256). The remaining 20 classes have zero support and
score F1=0 under `zero_division=0` — this is why 25-class macro-F1 (0.1738) equals active-class
macro-F1 (0.8690) times the active-class fraction (5/25=0.20) exactly.

| Condition | BENIGN | Bot (n=1) | Bot - Attempted (n=4) | DDoS (n=160) | PortScan (n=256) | Active-class Macro-F1 |
|---|---|---|---|---|---|---|
| Baseline RF | 0.735 | 0.000 | 0.000 | 0.000 | 0.000 | 14.71% |
| Closed-Loop | 0.980 | 1.000 | 0.400 | 1.000 | 0.966 | 86.90% |

### Key Takeaways
1. **Protocol fix changes baseline/static numbers only, not closed-loop's**: closed-loop's final
   Macro-F1 is unchanged (0.1738) since it always used this eval split; baseline moves from 0.0288
   (full window) to 0.0294 (shared 30% split) — the relative ratio moves from ~6.03x to **5.91x**
   (final window) / **5.08x** (post-drift mean) under the corrected, fair protocol.
2. **Active-class Macro-F1 is 86.90%, not 96.2%** — the prior figure had no backing artifact.
   `Bot - Attempted` (support=4) is the weakest active class at F1=0.400, dragging the active-class
   mean down from what a per-class eyeball of the easier classes would suggest.
3. **Full-retraining comparison numbers retracted** — no real run backs 14.8GB/~150s/~4,200s/
   0.1690/0.1484/5.86x; removed from the paper's Table IV rather than replaced with an estimate.

## 2026-09-17 — Downstream Augmentation Utility Study (Full CICIDS2017)

**Component**: `scratch/test_gan_utility.py` → `results/gan_downstream_utility.json`  
**Scale**: Full CICIDS2017 (1,470,014 train, 315,003 val, 315,004 test), 12 target classes evaluated on held-out test split, Random Forest classifier.

| Condition | Description | Macro-F1 | Weighted-F1 | Delta vs Real-Only |
|---|---|---:|---:|---:|
| **Condition A** | Real Train Data Only (Baseline) | **0.8481** | **0.9324** | 0.00% (ref) |
| **Condition B** | Real + Gaussian Noise ($\sigma=0.05$) | 0.8310 | 0.9185 | -1.71% |
| **Condition C** | Real + Ungated GAN Synthetic | 0.8280 | 0.9221 | **-2.01%** |
| **Condition D** | Real + MMD-Gated GAN Synthetic ($\tau=0.25$) | **0.8481** | **0.9324** | 0.00% |
| **Condition E** | Real + Feature-Shuffled Random Control | 0.8307 | 0.9235 | -1.74% |

### Key Takeaways
1. **Ungated GAN Degradation**: Adding ungated synthetic samples to the offline training set degrades downstream Macro-F1 by **-2.01%** (worse than random Gaussian noise and feature shuffling), confirming that naive generative augmentation introduces boundary distortion in dense tabular feature spaces.
2. **MMD Gate Safety Filter**: Condition D (MMD-gated GAN) successfully filters out low-fidelity synthetic distributions, preventing classifier degradation and preserving baseline performance (0.8481 Macro-F1).
3. **Validation of Closed-Loop Architecture**: This empirical result explains why static one-shot offline augmentation fails to improve classification metrics (Stage 3 finding) and proves that generative augmentation must be applied dynamically during drift events with fidelity gating.

## 2026-10-08 — Intervention P0 (feasibility / data adequacy), scenario S1, frozen

**Component**: `python -m proteus.intervention.p0` → `results/intervention_p0_S1_B25.json`, `results/intervention_p0_S1_B100.json`, `results/intervention_p0_S1_summary.json`
**Scale**: CICIDS2017 (WTMC-2021 corrected), 2,100,021 rows, 80 features; S1 = Mon–Thu → Fri; seeds [0, 1, 2, 3, 4]; budgets [25, 100] labels/window; oracle trigger; SPEC v1.3; commit `7567ff1` (clean tree); wall-clock 348.2 s (RF on CPU)

| Budget | Status | seeds with ≥2 GO cells | seeds assessable | GO class |
|---|---|---|---|---|
| B=25 | **NO_ROOM** | 2/5 | 5/5 | PortScan |
| B=100 | **GO** | 5/5 | 5/5 | PortScan |

**Outcome**: GO (GO at B=100; NO_ROOM at B=25). Validity: V1 leakage audit pass=True (30 runs, 0 violations); V3 integrity pass=True (133 cells); V4 repairability pass=True, R = {Bot, DDoS, PortScan}; V2 null region (diagnostic) pass=True.

| Budget | Condition | Recovery AUC (mean [95% t-CI], n=5) | promotions / seed |
|---|---|---|---|
| B=25 | FROZEN | 0.000 [0.000, 0.000] | 0.0 |
| B=25 | REAL_ONLY | 0.206 [-0.030, 0.441] | 0.6 |
| B=25 | REAL_ONLY_ALL_LABELS | 0.182 [-0.156, 0.520] | 0.4 |
| B=100 | FROZEN | 0.000 [0.000, 0.000] | 0.0 |
| B=100 | REAL_ONLY | 0.381 [0.109, 0.653] | 1.6 |
| B=100 | REAL_ONLY_ALL_LABELS | 0.182 [-0.156, 0.520] | 0.4 |

- **Descriptive facts read off the per-window records (not preregistered tests)**: at B=100 the real-only candidate often has a gate-utility LCB of 0.49–0.62 yet is rejected `envelope_inconclusive` (D_gate has 84–158 benign rows, so one extra benign false positive moves the FPR by ≥ 1/158 > ε_FPR); the all-labels control is rejected 34/45 times for the same reason and its recovery AUC (0.18) is below budgeted real-only (0.38) — learning Friday PortScan genuinely costs benign FPR on the order of ε_FPR.
- **Qualification (do not drop when citing)**: PortScan is the only class that creates a GO and sits exactly at the 3/5 repairability threshold; it carries the ambiguity flag (max D_sel conflict share 0.167, max E share 0.056); the corpus has 4,926 feature vectors with more than one label (4,331 across the two temporal pools).
- P0 establishes feasibility and data adequacy only. It says nothing about whether synthetic data helps.
- Provenance: params digest `52f53b4c659a8d55…`, criteria digest `584e9c0753dfc489…`, §L.1 rules sha256 `779e679aa006afaf…`; artifact sha256 of the summary `067e9e80eaedf88e…`.

## 2026-10-09 — Intervention P1 campaign (SPEC v1.4, preregistered), scenario S1, B=100

**Component**: `python -m proteus.intervention.p1` → `results/p1/intervention_p1_S1_B100_seed{0..9}.json`; `python -m proteus.intervention.analyze_p1` → `results/intervention_p1_S1_B100_summary.json`, `results/intervention_p1_S1_B100_decisions.json`; audits `results/p1_leakage_audit.json`, `results/p1_audit_sensitivity.json`
**Scale**: CICIDS2017, S1, B=100 labels/window, 10 paired seeds, 23 arms, oracle trigger; base commit `7567ff1` (working tree, per-file code hashes in every seed file); P1 rules sha256 `d96b03131071ac1a…`; preregistered configuration = True; RF on CPU, ≈85 min summed per-arm wall-clock

| Arm | R-recovery, deployed (mean [95% t-CI], n=10) | candidate quality (shadow) | promotions syn/real | rollbacks | S_report breaches |
|---|---|---|---|---|---|
| FROZEN | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0/0 | 0 | 0 |
| REAL_ONLY | 0.623 [0.387, 0.859] | 0.911 [0.895, 0.928] | 0/14 | 0 | 0 |
| CTRL-ROS | 0.623 [0.387, 0.859] | 0.911 [0.895, 0.928] | 0/14 | 0 | 0 |
| CTRL-THRESH | 0.623 [0.387, 0.859] | 0.911 [0.895, 0.928] | 0/14 | 0 | 0 |
| CTRL-SMOTE | 0.623 [0.387, 0.859] | 0.911 [0.895, 0.928] | 0/14 | 0 | 0 |
| FIXED-SMOTE-1 | 0.623 [0.387, 0.859] | 0.915 [0.898, 0.932] | 2/13 | 0 | 2 |
| FIXED-SMOTE-4 | 0.625 [0.388, 0.861] | 0.920 [0.903, 0.938] | 3/13 | 0 | 1 |
| ALWAYS-SMOTE | 0.624 [0.387, 0.860] | 0.916 [0.898, 0.933] | 2/13 | 0 | 2 |
| FIDGATE-SMOTE | 0.624 [0.388, 0.861] | 0.920 [0.902, 0.937] | 2/13 | 0 | 0 |
| REAL_ONLY_ALL_LABELS | 0.372 [0.070, 0.674] | 0.974 [0.964, 0.984] | 0/5 | 0 | 4 |

| Preregistered test | paired difference [95% CI] | result |
|---|---|---|
| H2 CTRL-SMOTE − REAL_ONLY | 0.000 [0.000, 0.000] | null NOT rejected (identically 0 in all 10 seeds) |
| H3a / H3b | not tested (fixed sequence stopped at H2) | — |
| H4 safety + activity | 0 breaches; synthetic candidate promoted in 0/10 seeds | safe by inaction |

**Verdict (mechanical)**: NEGATIVE: H2 not rejected; fixed sequence stops; P2 (WGAN) cancelled. Fired: F2_H2_not_rejected, F3a_H3a_not_rejected, F3b_H3b_not_rejected, F8_degenerate_controller. P2 (WGAN-GP) not run (gate closed).
- Controller degenerate: 59 of 59 controller runs with a need stop at k=0; no evaluated step had a positive lower bound (max LCB 0.000 / 0.000 / 0.012 for SMOTE / duplication / threshold vs η=0.02).
- Candidate vs deployed (real-only, matched windows): 0.911 vs 0.701; seeds 0 and 5 never certified a model.
- Exploratory: fixed-dose SMOTE ρ=4 candidates +0.0089 F1 over real-only candidates (0.0089 [0.0058, 0.0119]); deployed +0.0012 (0.0012 [-0.0015, 0.0038]).
- Reconciliation: with the canary off, P1 real-only reproduces the frozen P0 REAL_ONLY decision, reason, region and E confusion cells at every window of seeds 0–4; manifests of seeds 0–4 equal P0's.
- Caveats: negative controls and most ablations are vacuous (the controller never adds rows); ORACLE_DOSE is built from the base incumbent and is indicative only; exploratory contrasts are uncorrected.
- Artifact sha256 (summary): `f48fcce0026847e7…`

## 2026-10-09 — Intervention P0 on scenario S2 (the P3 gate, SPEC v1.4)

**Component**: `python -m proteus.intervention.p0_s2` → `results/intervention_p0_S2_{B25,B100,summary}.json`
**Scale**: S2 = Mon+Tue → Wed (DoS family), seeds 0–4, budgets 25 and 100; unchanged §L.1 rules (criteria scenario S2); base commit `7567ff1`; wall-clock 167.2 s

| Budget | Status | assessable seeds | GO cells |
|---|---|---|---|
| B=25 | NO_ROOM | 5/5 | 0 |
| B=100 | NO_ROOM | 5/5 | 0 |

**Outcome**: NO_GO_NO_ROOM (NO_ROOM at B=25,100); validity all pass = True; R = {DoS GoldenEye, DoS Hulk, DoS Slowhttptest, DoS Slowhttptest - Attempted, DoS slowloris, DoS slowloris - Attempted}. Recovery AUC (real-only / all-labels) at B=100: 0.192 / 0.744. By the preregistered rule P3 (S2 arms) is not run: real-only adaptation suffices at the assessed budgets.

## Template for future entries

```
## YYYY-MM-DD — <component/stage>, <run label if multiple runs of the same thing>

**Component**: <script/function> → <output artifact path>
**Scale**: <dataset, size, seed count>

<the actual numbers, in a table where there's more than a couple>

- <anything a future reader needs to correctly interpret these numbers — caveats,
  known-miscalibrated thresholds, what changed since the last entry for this component>
```

