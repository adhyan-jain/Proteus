# Known Limitations (as of 2026-09-17)

Read alongside `STATUS.md` (operational handoff) and `docs/AUTONOMOUS_AUDIT_LOG.md` (how these
were found). This file is the single place that answers "what genuinely still isn't done, and
why." Only real, currently-true blockers belong here — not stale gaps already closed.

## 1. Incremental Adaptation Rerun Completed & 5-Seed Statistical Confidence Sweep

The closed-loop evaluation mechanism has been refactored from full-dataset retraining to a genuine bounded-memory adaptive retraining mechanism (`BoundedBufferClassifier`) and executed under strict non-leakage invariants (`split_eval_fit` across identical 30% held-out splits for all conditions).
- **Memory Complexity**: $O(1)$ constant memory footprint capped at $|D_{\text{adapt}}| \le 25,000$ rows ($N_{\text{ref}} = 20,000$ reference reservoir + $N_{\text{recent}} = 5,000$ sliding adaptation buffer).
- **Update Latency**: Reduced from ~150s per drift step to ~2.5s–3.7s per drift step.
- **Single-Seed Evidence (n=1)**: Executed and verified (759.4s wall-clock time across all 3 conditions). Final window Macro-F1: **0.1738** vs Baseline **0.0294** (**5.91x retention**; post-drift mean 0.1495 vs 0.0294, 5.08x). Active-class Macro-F1: **86.90%** across the 5 active classes.
- **Statistical CI Sweep (n=5)**: For a multi-seed paper claim (project rule: 5+ seeds with mean + 95% CI), run:
```bash
.venv/bin/python -c "from proteus.evaluate_full import run_stage7; run_stage7(n_seeds=5)"
```
Budget ~50-60 minutes total for 5 seeds.

## 2. Live Mininet/Ryu integration — blocked on root access, unchanged

`sdn/topology/smoke_test.sh` requires `sudo`; this environment has no sudo access. Everything
upstream of it (topology, controller app, feature mapper, traffic generators) is written and
independently verified (see `STATUS.md`'s "Blocked" section for exact verification status per
file). `LiveMininetSource` in `proteus/closed_loop_full.py` is a deliberate `NotImplementedError`
stub for exactly this gap. **What the repo owner needs to run**: `sudo bash
sdn/topology/smoke_test.sh`, then wire `ryu_ids_app.py::on_schema_row` to a real
`LiveMininetSource` implementation.

## 3. Fidelity gate: 44% real-batch admission rate is an open, not-yet-resolved tension

Stage 4 (`METRICS_HISTORY.md`, 2026-09-11) found the MMD fidelity gate correctly rejects 100% of
injected noise (safety-critical direction, perfect) but only admits 4/9 (44%) of real
WGAN-GP-generated batches from classes that already passed Stage 3's per-class diversity
diagnostic (not mode-collapsed, not over-dispersed). This is a real disagreement between two
different fidelity signals (per-class diversity vs. distribution-level MMD), not a bug — but it
is not resolved, and the paper reports it as an open question rather than papering over it.

## 4. GAN static augmentation did not improve the baseline (Stage 3, real finding, not a defect)

Baseline macro-F1 0.8922 vs. static-augmentation 0.8915 (marginally lower). This is reported
honestly as a negative/null result for one-shot offline augmentation — it is the reason the
project's actual contribution claim rests on the *closed-loop, drift-triggered* condition
(limitation #1), not on static augmentation alone.

## 5. Citations in the paper are not independently verified against a live database

`paper/main.tex`'s references are limited to well-established, canonical works (Goodfellow et
al. 2014; Arjovsky et al. 2017; Gulrajani et al. 2017; Gretton et al. 2012; Breiman 2001;
Sharafaldin et al. 2018; Elsayed et al. 2020) that this session did not re-verify via a live
web/database search. These are widely-cited, standard references in their respective areas; a
final pre-submission pass should still verify exact venue/page details against a citation
manager before submission.

## 6. `.agents/hooks.json` — unresolved security artifact, repeated flag

Untracked, unconditional tool-call auto-approve hook, origin unknown. Flagged by a prior session
and again by this one. Deliberately left untouched — a repo-owner decision, not an agent one.

## 7. Test coverage expanded across core components

Unit tests cover:
- Closed-loop leakage prevention and evaluation partition isolation (`tests/test_closed_loop_leakage.py`).
- MMD unbiased finite-sample behavior, non-clamping, and diagonal exclusion (`tests/test_fidelity.py`).
- Drift detection semantics (`tests/test_drift.py`).
- Bounded-buffer adaptive classifier memory and latency constraints (`tests/test_incremental_adaptation.py`).
- API server inference, health, and metrics endpoints (`tests/test_api_server.py`).

## 8. Pre-Drift Stream Index Overlap Semantics

Pre-drift stream evaluation windows ($w_0..w_5$) are sampled randomly from the Monday–Thursday stable pool. Because offline baseline training utilizes 1,200,000 samples from the 1,552,454 Monday–Thursday rows (~77.3%), empirical auditing (`scratch/audit_predrift_duplicates.py`) confirms that ~76.8% of the pre-drift evaluation window indices were seen during initial offline fitting. 
- **Pre-Drift Role**: Acts as an in-distribution retention and stability validation benchmark (active-class Macro-F1 = 100.0% across active classes).
- **Post-Drift Role**: Post-drift evaluation windows ($w_6..w_{15}$) are drawn strictly from Friday data (unseen attack families `Bot`, `DDoS`, `PortScan`), ensuring **0.0% overlap** with the offline training dataset.
