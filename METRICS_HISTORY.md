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

## Template for future entries

```
## YYYY-MM-DD — <component/stage>, <run label if multiple runs of the same thing>

**Component**: <script/function> → <output artifact path>
**Scale**: <dataset, size, seed count>

<the actual numbers, in a table where there's more than a couple>

- <anything a future reader needs to correctly interpret these numbers — caveats,
  known-miscalibrated thresholds, what changed since the last entry for this component>
```
