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

## Template for future entries

```
## YYYY-MM-DD — <component/stage>, <run label if multiple runs of the same thing>

**Component**: <script/function> → <output artifact path>
**Scale**: <dataset, size, seed count>

<the actual numbers, in a table where there's more than a couple>

- <anything a future reader needs to correctly interpret these numbers — caveats,
  known-miscalibrated thresholds, what changed since the last entry for this component>
```
