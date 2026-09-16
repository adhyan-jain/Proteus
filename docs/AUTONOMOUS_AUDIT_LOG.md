# Autonomous Audit Log — 2026-09-17

Chronological record of an autonomous audit/completion/paper-preparation session. Read
`STATUS.md` first for the current handoff state; this file is the "how we got here today" trail
for *this specific session*, in the spirit of `CHANGELOG.md` but scoped to one sitting.

## Initial state (commit `0d67b84`)

- Working tree clean except untracked `.agents/hooks.json` (pre-existing, flagged by a prior
  session as a security-relevant artifact — an unconditional tool-call auto-approve hook,
  origin unknown, deliberately left untouched again this session — see "Security" below) and
  `logs/` (pre-existing run logs).
- `torch==2.11.0+cu128`, `torch.cuda.is_available() == True`, CUDA 12.8, RTX 4060 confirmed via
  direct check (not assumed).
- Machine memory: **critical pressure at audit start** — `free -h` showed 12/15Gi RAM used,
  17/22Gi swap used, ~217-473Mi free RAM, *before* this session started any work of its own.
  `ps aux --sort=-%mem` showed the load came from Ollama, a Chrome renderer, VS Code, and a
  ClickHouse server — all pre-existing, unrelated processes, not anything this session started.
  This materially constrained what could safely be run (see "What was not run" below).
- No `pytest` installed in `.venv`; the only existing test file in the repo was
  `sdn/topology/test_feature_mapper.py` (unittest, `.venv-ryu`-scoped, unrelated to the main
  backend). The main Python backend (`proteus/`) had **zero tests** before this session.

## Discovered issues

1. **Critical: train/test leakage in the closed-loop condition's reported metric**
   (`proteus/closed_loop_full.py::ClosedLoopOrchestrator.step()`, and the identical pattern in
   the demo's `proteus/pipeline.py::run_pipeline`). On a fired drift event, the classifier was
   retrained on `(accumulated training set + current window)`, then `macro_f1_after` was scored
   on that *same* current window — in-sample training accuracy reported as a post-adaptation
   generalization metric. The baseline/static-augmentation conditions were, by contrast, always
   scored on windows they never trained on (`_eval_frozen` in `evaluate_full.py`). This made the
   project's flagship result (2026-09-12 METRICS_HISTORY entry: closed-loop 0.199 vs. baseline
   0.029 macro-F1, "~6.9x") an unfair comparison as originally reported.
2. Dead code: unused `import numpy as np` in `proteus/baseline.py`; unused `copy`, `json`, `time`
   imports in `proteus/closed_loop_full.py`; an assigned-but-never-read `static_admission_log`
   local in `proteus/pipeline.py`.
3. A silently-swallowed exception (`except Exception: pass`) in `proteus/pipeline.py`'s
   static-augmentation loop — a per-class GAN-generation or fidelity-check failure would vanish
   with no trace in `results`.
4. No automated tests existed for `proteus/fidelity.py` (MMD gate) or `proteus/drift.py` (KS-test
   detector) despite both being safety/validity-critical, well-isolated, pure-computation
   modules that don't require GPU or the full dataset to test meaningfully.

## Fixes applied (see `CHANGELOG.md` for the user-facing summary, git log for exact diffs)

- `ClosedLoopOrchestrator.split_eval_fit()` — new `@staticmethod`: splits every incoming window
  into a fit portion (all that ever reaches training / GAN resume-training) and a held-out eval
  portion (never trained on that round, fixed `np.random.default_rng(123)`), before any
  adaptation touches it. `macro_f1_before`/`macro_f1_after` now both measured on the eval
  portion only. Unit-tested directly (no GPU/checkpoint needed — pure numpy) in
  `tests/test_closed_loop_leakage.py`.
- `proteus/pipeline.py::_split_eval_fit` — same fix, same pattern, applied independently to the
  demo backend's closed-loop condition (kept as a separate function since the demo and
  full-scale pipelines are intentionally independent implementations).
- Removed the four dead-code items above; the swallowed exception now appends
  `{"class": ..., "error": ...}` to a new `results["static_augmentation_errors"]` list instead
  of vanishing.
- Added `tests/` (new, `pytest` installed into `.venv` via `uv pip install`, `TMPDIR` redirected
  per `CLAUDE.md` rule 9): 14 tests across `test_fidelity.py`, `test_drift.py`,
  `test_closed_loop_leakage.py`. All pass (`pytest tests/ -q` → `14 passed`).
- Ran the actual demo pipeline end-to-end (`proteus.pipeline.run_pipeline()`) as a smoke test
  after the fix: completed in well under a 180s timeout, `data_source: synthetic-fallback`
  (no network download attempted/available in this pass — expected, honestly reported by the
  pipeline itself, not something this session forced), all three conditions produced consistent
  macro-F1 series, no exceptions. This validates the fix doesn't break the demo path.

## What was NOT run, and why (read before assuming a gap is negligence)

- **The full-scale Stage 7 rerun** (`proteus.evaluate_full.run_stage7()`), needed to produce a
  *valid* closed-loop-vs-baseline number after the leakage fix. The pre-fix single-seed run took
  4,199s (~70 min) and loads/trains against a 1.2M-row pool with multiple full RandomForest
  refits. Given this machine had ~217-473Mi free RAM and 17/22Gi swap already in use from
  *other, unrelated* processes at the time of this audit (not something this session could or
  should stop), launching a multi-hour heavy job risked exactly the kind of OOM/thrash crash
  this repo already documented once (`CHANGELOG.md`/`STATUS.md`'s 2026-09-13 CPU-spike entry) —
  this time with a real chance of taking down the user's other active work (browser, editor,
  other agent sessions), not just this one. This was a judgment call to flag rather than a
  silent omission — see `docs/KNOWN_LIMITATIONS.md` for the exact rerun command and the
  condition (machine not under concurrent heavy load) under which it's safe to run.
- **The 5-seed sweep** (`run_stage7_5seed.py`) — same reasoning, at 5x the cost.
- **Live Mininet/Ryu integration** — unchanged from `STATUS.md`'s prior "Blocked" section: needs
  root access this environment does not have. Nothing new attempted here; still exactly the
  documented blocker.
- **A from-scratch literature-database verification of citations** — this session did not run a
  live web-search pass against each reference in the paper's bibliography; the references
  included are limited to well-established, canonical papers (original GAN, WGAN-GP, MMD,
  CICIDS2017, InSDN, Random Forest) this session is confident are real and correctly attributed,
  not run through a citation-verification tool. See `docs/PAPER_EVIDENCE_MAP.md` for exactly
  which claims in the paper are execution-backed vs. narrative/background.

## Security note (unchanged from prior session, re-verified, still unactioned)

`.agents/hooks.json` (untracked, not committed) configures a `PreToolUse` hook that
unconditionally auto-approves every tool call (`"*" -> "allow"`). Re-inspected this session,
contents confirmed unchanged. This is a real security-relevant artifact (it would silently
bypass every permission prompt for any tool, in any future session, for anyone using this
repo directory) and was, again, deliberately left in place and untouched rather than silently
deleted or silently trusted — this is the repo owner's call to make, not an agent's.

## Outcome

See `docs/END_TO_END_VALIDATION.md` for the final pass/fail matrix and `docs/VALIDATION.md` for
what was actually executed with commands and outcomes.
