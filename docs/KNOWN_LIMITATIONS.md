# Known Limitations (as of 2026-09-17)

Read alongside `STATUS.md` (operational handoff) and `docs/AUTONOMOUS_AUDIT_LOG.md` (how these
were found). This file is the single place that answers "what genuinely still isn't done, and
why." Only real, currently-true blockers belong here — not stale gaps already closed.

## 1. Incremental Adaptation Rerun Completed & 5-Seed Statistical Confidence Sweep

The closed-loop evaluation mechanism has been refactored from full-dataset retraining to a genuine incremental streaming mechanism (`BoundedBufferClassifier`) and executed under strict non-leakage invariants (`split_eval_fit`).
- **Memory Complexity**: $O(1)$ constant memory footprint capped at $|D_{\text{adapt}}| \le 25,000$ rows ($N_{\text{ref}} = 20,000$ reference reservoir + $N_{\text{recent}} = 5,000$ sliding adaptation buffer).
- **Update Latency**: Reduced from ~150s per drift step to ~2.5s–3.7s per drift step.
- **Single-Seed Evidence (n=1)**: Executed and verified (654.0s wall-clock time). Final window Macro-F1: 0.1738 vs Baseline 0.0288 (**~6.03x retention**).
- **Statistical CI Sweep (n=5)**: For a statistically validated paper claim (project rule: 5+ seeds with mean + 95% CI), run:
```bash
.venv/bin/python -c "from proteus.evaluate_full import run_stage7; run_stage7(n_seeds=5)"
```
Budget ~50-60 minutes total for 5 seeds (thanks to the sub-second/few-second incremental adaptation latency).

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

## 7. Test coverage is real but narrow

`tests/` (new this session) covers `fidelity.py`, `drift.py`, and the leakage-fix invariant in
`closed_loop_full.py` — all pure-computation, GPU-free, dataset-free paths chosen specifically so
they run safely under this session's memory constraints. It does **not** cover `gan_full.py`
tensor-shape/device-handling, `data_full.py` preprocessing correctness, or `baseline_full.py`
end-to-end — those require either GPU tensors or the real ~1.2GB CICIDS2017 CSV loaded into
memory, both of which were deferred for the same memory-pressure reason as limitation #1. Adding
small-fixture (not full-scale) tests for `data_full.py`'s column-mapping/label logic would be
the highest-value next addition and does not require heavy compute.
