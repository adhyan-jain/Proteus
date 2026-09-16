# Proteus — Changelog / Evolution

Chronological record of how the pipeline got to its current shape, including where the plan
itself changed mid-project and why. This is a narrative log, not a commit-by-commit mirror —
see `git log` for that. Dates are when the work happened (this machine's local time). For
current running state and open items, see `STATUS.md` — this file explains history, `STATUS.md`
is the live handoff point.

## 2026-09-10 — Demo proof-of-concept (40-minute build)

Built a scaled-down, end-to-end demo under a hard time budget: NSL-KDD (or a synthetic
NSL-KDD-schema fallback, clearly labeled) → Random Forest baseline → small WGAN-GP (minority-class
augmentation) → KS-test (Kolmogorov-Smirnov) drift detector → MMD fidelity gate → a simulated
traffic stream with injected drift events → a three-condition evaluation (baseline /
static-augmentation / closed-loop) → a Streamlit UI. Explicitly not the full architecture —
no real SDN deployment, small-scale data, single run. This became the permanently-frozen demo
(`app.py` + `proteus/{data,baseline,gan,drift,fidelity,stream,pipeline}.py`).

## 2026-09-10 (later) — Paper-grade backend scale-up begins

Git repo initialized (had none before). Stage 1 of a from-scratch full-scale rebuild: real
CICIDS2017 (WTMC-2021 corrected, from its own project page — DistriNet/KU Leuven) downloaded,
unified feature schema built (`proteus/data_full.py`), 2.1M rows, 25 real label classes,
stratified 70/15/15 split. InSDN downloaded via Kaggle (a community re-upload, not yet an
official source at this point) and integrated with a verified positional column-name mapping
onto the same schema.

Also in this window: Ryu 4.34 got working in a dedicated Python 3.8 venv after hitting and
fixing three real compatibility breaks in sequence (old-setuptools install hook, a removed
`eventlet` constant, an unpinned transitive `dnspython` dependency, and a missing legacy
`oslo.config` namespace package) — documented as a reproducible script
(`sdn/setup_ryu_venv.sh`), not just a one-off fix. OVS (Open vSwitch) services enabled.

## 2026-09-10 (later still) — Frontend rebuild + UI polish requests

A separate, much larger frontend effort: a new Next.js "SOC console"-styled mission-control UI
(`frontend/` + a new read-only `api/` FastAPI layer), explicitly *not* replacing the Streamlit
demo — built alongside it. Real design constraints given (avoid generic-dashboard/AI-gradient
look, semantic color system, no fabricated metrics, explicit empty states). Built with
locally-installed Playwright (no Playwright MCP tool exists in this installation) driving a
real screenshot/console-error QA loop across all routes and several viewport sizes; one real
animation-cutoff chart bug was found and fixed this way.

Separately, the Streamlit demo's own architecture diagram got two rounds of fixes on direct
request (an overlapping-annotation rendering bug, then a broader "more detail + click-to-explain
nodes + expand every abbreviation" pass) — the demo stayed otherwise untouched per the standing
freeze rule.

## 2026-09-11 — Stricter full-scale rules; InSDN re-sourced; GPU rule established

The scale-up's rules tightened significantly: no synthetic-data fallback of any kind for
CICIDS2017/InSDN (a hard stop-and-report requirement, not a soft preference), every dataset
source must be independently verifiable (an official/institutional page, not "a download that
worked"), no placeholder metrics anywhere, minimum 5 random seeds with confidence intervals for
any final reported result, and a full live Mininet+Ryu deployment requirement (Stage 5-7).

Two real problems found and fixed as a direct result of applying this stricter bar:

1. **InSDN's source didn't meet the new bar.** The Kaggle re-upload used earlier was replaced
   with the actual official distribution — UCD ASEADOS Lab's own page
   (`aseados.ucd.ie/datasets/SDN/`), the home institution of the dataset's original authors
   (Elsayed, Le-Khac & Jurcut, IEEE Access 2020). Verified identical underlying data (matching
   row counts across all three source files) before switching `proteus/data_full.py` over.

2. **Training had been running on CPU the entire time despite a real GPU (RTX 4060, 8GB) being
   present on this machine** — a CPU-only torch wheel (`+cpu`, from
   `download.pytorch.org/whl/cpu`) had been installed instead of a CUDA build, and nobody had
   checked `torch.cuda.is_available()` before launching training. This is now an absolute rule
   (`CLAUDE.md`/`AGENTS.md` rule 1): verify GPU availability before every training run, never
   silently proceed on CPU. The in-progress full-scale WGAN-GP training run was stopped and
   restarted after reinstalling torch with CUDA 12.8 support.

**Also discovered**: the shared `.venv` had `torch` silently removed at some point, almost
certainly a side effect of another concurrent agent's package installation into the same
environment (everything else in the venv was intact — only `torch` itself was gone, its
dependencies like `sympy`/`networkx` remained). Reinstalled; added an explicit rule against
running any "sync to exact requirements" style command against the shared venv going forward.

**Real blocker, not yet resolved**: Mininet is still not installed on this machine. It requires
an interactive `sudo` session the repo owner has to run themselves (an agent cannot supply a
sudo password, and Mininet needs root privileges at *runtime*, not just at install time, so this
isn't a one-time hurdle that can be worked around). Stage 0's smoke test, and everything in
Stages 5-7 that depends on a live Mininet/Ryu deployment, is blocked on this until the repo
owner runs the install themselves.

**Also discovered mid-session**: a background training process, once detached via plain shell
backgrounding from inside a subagent, did not reliably survive that subagent being stopped —
contrary to the assumption that a `nohup`'d process is fully independent of its parent agent
session. Treat any long-running background job as at-risk if the agent that launched it gets
stopped; verify it's still alive with a fresh `ps` check rather than assuming.

## 2026-09-11 (later) — Full-scale WGAN-GP trained on GPU; real, mixed diversity results

Restarted Stage 3's WGAN-GP training clean after the GPU fix (previous CPU run had also died
mid-way, likely collateral from an earlier agent-stop event). 80 epochs, ~30 minutes wall-clock
on the RTX 4060 (vs. an estimated ~65+ minutes the same run would have taken on CPU at the rate
observed before). GPU utilization during training was modest (~8%) — this particular model
(3-layer generator/critic, batch size 64) is small enough that per-step Python/numpy batch
construction dominates over GPU compute time; the GPU rule is satisfied (training genuinely runs
on CUDA, not silently falling back to CPU) but this is not a compute-bound workload, worth
knowing honestly rather than implying a bigger speedup than what actually happened.

The loss-plateau stopping criterion never triggered — generator loss climbed from ~5.5 to
~212 over the full 80 epochs and never dropped below the configured std threshold, even though
by the last ~10 epochs the loss had visibly flattened out numerically (208-212 range). The
threshold as configured is miscalibrated for a loss at this scale; this is a diagnostic-code
issue to fix before relying on the plateau criterion for early stopping in a future run, not
evidence the generator failed to train.

**Real, honest finding from the diversity diagnostics** (built to catch mode collapse — real
attack samples vs. generated ones, per class, compared by mean pairwise distance): **zero
classes showed mode collapse** (the classic failure mode: generator producing near-identical
samples). But the diagnostic as originally written only checked for *under*-diversity — it
would have silently missed the opposite failure, which did occur: **3 of 12 GAN-target classes
show generated samples far more scattered than the real distribution** ("Bot - Attempted" at
~3160x the real class's pairwise distance, "DoS slowloris - Attempted" at ~11x, "FTP-Patator" at
~3.2x, borderline). This means the generator hasn't actually learned those classes' real
(sometimes very tightly-clustered) distributions — it's producing statistically implausible,
over-scattered synthetic data for them, not useful augmentation. Added a symmetric
`likely_overdispersed` flag (ratio > 3.0, mirroring the existing `likely_mode_collapse` at
ratio < 0.3) to `proteus/gan_full.py` so this failure mode is caught automatically going
forward, and recomputed diagnostics from the saved epoch-80 checkpoint with the new flag.
Real numbers in `results/gan_full_diagnostics.json`.

**Not yet decided**: whether these 3 over-dispersed classes are an acceptable, documented
limitation for Stage 3's "sanity check must pass" bar, or whether they need another training
attempt (more epochs, different learning rate, or excluding them from GAN augmentation like the
already-excluded too-rare classes) before Stage 4 begins — this is a real judgment call to make
with the repo owner, not something to silently wave through or silently fix by lowering the bar.

## 2026-09-11 (later) — Pipeline diagram click-to-describe

The Next.js Overview page's closed-loop pipeline diagram (`frontend/src/components/pipeline/
pipeline-diagram.tsx`) previously only showed live run data per stage, with no way to click a
stage for a plain-language explanation — a real request from earlier in the project that was
never implemented. Each of the 8 stage cards is now a button; clicking one toggles a short
(1-3 sentence) explanation of what that stage does in an info panel below the grid, styled to
match the existing SOC-console design system (network-accent border/text, mono label). Default
state shows a neutral "click a stage above to see what it does" prompt rather than nothing.
Verified with a local Playwright script driving the running dev server: default prompt renders,
clicking a stage swaps in its explanation, clicking the same stage again toggles back to the
default, and `npm run build` passes with no TypeScript errors.

## 2026-09-11 (later still) — Stage 5: Mininet topology + Ryu IDS controller app (written, not yet run)

With Mininet 2.3.1b4 now installed on this machine, built the pieces Stage 0's smoke test and
Stage 5 need: a trivial 4-host/2-switch Mininet topology (`sdn/topology/topo.py`, run under
system python3 since Mininet lives there, not `.venv-ryu`) pointed at a real Ryu controller app
(`sdn/topology/ryu_ids_app.py`, `.venv-ryu`), extending `ryu.app.simple_switch_13` with L2
forwarding widened to match on L3/L4 fields plus a periodic OpenFlow flow-stats poll.

The flow-stats export is mapped onto `proteus/data_full.py`'s unified schema column-naming
convention by a new pure function, `sdn/topology/feature_mapper.py`, deliberately factored out
stdlib-only so it's unit-testable without importing ryu. Its docstring is explicit about the
real gap between what CICFlowMeter computes over a completed bidirectional flow (~80 features
incl. inter-arrival-time stats, TCP flag counts, backward-direction everything) and what a live
OpenFlow flow-stats poll can give (aggregate packet/byte counters, duration, ports, protocol) —
10 schema columns are honestly derivable, the rest are left absent rather than fabricated.
7 unit tests, all passing.

This session had no sudo access, and Mininet requires root at runtime (not just install time),
so none of this could be run end-to-end here — only syntax/import-checked, and `ryu-manager
--verbose` confirmed to load the app cleanly with no live switch involved. A smoke-test script
(`sdn/topology/smoke_test.sh`) is written for the repo owner to run with `sudo`, doing exactly
what Stage 0 originally asked: bring the topology up, confirm the controller attaches, inject a
benign and an attack-like traffic sample (via a new stdlib-only `gen_traffic.py`, since
hping3/nmap aren't installed here), confirm both flow through the controller path, tear down
cleanly. See `STATUS.md`'s Blocked section for the exact command and what success looks like.
Stage 6 (wiring a trained classifier onto this live stream) is intentionally not started —
`ryu_ids_app.py`'s `on_schema_row()` is the documented extension point for it.

## 2026-09-13 — CPU-thread-oversubscription bug: the earlier partial fix didn't actually fix it

The repo owner reported the pipeline spiking CPU hard enough to throttle the machine and kill
VS Code windows outright — corroborated by `logs/stage7_5seed_20260913_035210.log`, a 5-seed
Stage 7 sweep attempt that died right after the initial CSV load, before any real training even
started.

A prior session (see the `proteus/baseline*.py`/`closed_loop_full.py`/`validate_full.py` diffs
already in the tree, plus the new `proteus/config.py`) had already tried to fix this: cap
`RandomForestClassifier(n_jobs=...)` to 4 instead of `-1` (all cores), and set
`OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS`/`MKL_NUM_THREADS`/`VECLIB_MAXIMUM_THREADS`/
`NUMEXPR_NUM_THREADS` env vars via `proteus/config.py::configure_environment()`, called at
import time. **This fix was silently a no-op everywhere it had been applied.** OpenBLAS/MKL/
OpenMP read those env vars exactly once, at their own C-extension init time (i.e. the moment
`numpy`/`torch`/`sklearn` is first imported in the process) — and in every file that imported
`proteus.config`, `numpy`/`torch`/`sklearn`/`pandas` had already been imported *first*, on the
line above. Setting the env vars after that point does nothing: each library had already spun up
its thread pool at the hardware default (`os.cpu_count()` = 16 on this machine). Net effect
before this fix: `n_jobs=4` capped joblib's *process* count, but each of those 4 worker
processes still ran full-width (16-thread) BLAS/OpenMP math underneath — up to **4 × 16 = 64
threads on a 16-core machine**, which is what was actually pinning the CPU.

Fixed by reordering imports so `proteus.config` (or `from proteus.config import DEFAULT_N_JOBS`)
is always the *first* import — ahead of `numpy`/`torch`/`pandas`/`sklearn` — in every module that
is a real or potential process entrypoint: `proteus/evaluate_full.py`, `baseline_full.py`,
`closed_loop_full.py`, `validate_full.py`, `baseline.py`, `pipeline.py`, `gan_full.py`,
`data_full.py`, and (with the repo owner's explicit approval, since it's normally frozen —
`CLAUDE.md` rule 7) `app.py`. Pure import-order change, no logic/API changes anywhere.

Verified two ways, not just by inspection: (1) `import proteus.config` then `import numpy`
confirms `OMP_NUM_THREADS` is set before numpy loads; (2) after importing the fixed modules,
`threadpoolctl.threadpool_info()` shows every actual backend — numpy's OpenBLAS, torch's OpenMP,
scipy's OpenBLAS, sklearn's OpenMP — reporting `num_threads: 4`, not 16. Also smoke-tested
`streamlit run app.py` after its edit: boots clean, HTTP 200, no errors.

**Lesson for future thread-cap or env-var-based config in this repo**: an env var read once at a
C-extension's import/init time cannot be set after that extension is already imported anywhere
in the process — order matters transitively through the whole import chain, not just within one
file. Any new module doing heavy numeric work (numpy/torch/pandas/sklearn/scipy) must import
`proteus.config` as its literal first import, before anything else.

## 2026-09-17 — Closed-loop leakage fix, bounded-buffer incremental adaptation, and paper draft

Two sessions in sequence on the same day found and fixed a real train/test leakage bug, then
replaced the retraining mechanism it exposed as too slow to re-validate safely.

**Leakage bug** (first session): `ClosedLoopOrchestrator.step()` (and the identical pattern in
the demo's `proteus/pipeline.py::run_pipeline`) retrained the classifier on
`(X_train ∪ current_window)` and then scored `macro_f1_after` on that same window — in-sample
training accuracy reported as a post-adaptation metric, not comparable to the baseline/static
conditions' honestly-held-out scoring. Fixed via `ClosedLoopOrchestrator.split_eval_fit`
(`proteus/pipeline.py::_split_eval_fit` for the demo): every incoming window is split into a
fixed-fraction held-out eval partition (never trained on) and a fit partition (all that ever
reaches training), before any adaptation happens. Unit-tested in
`tests/test_closed_loop_leakage.py`. This invalidated the prior 2026-09-12 Stage 7 result
(`METRICS_HISTORY.md`'s 2026-09-17 correction entry) — the rerun needed to get a valid number
was judged too expensive/risky to launch on a memory-pressured shared machine using the
then-current retraining approach (full-history Random Forest refit every drift event, ~2.5 min
per step, growing without bound).

**Bounded-buffer incremental adaptation** (second session): replaced full-history refit with
`BoundedBufferClassifier` — a fixed-size reference reservoir (20,000 rows, sampled once from
initial training) plus a sliding recent-adaptation buffer (5,000 rows, FIFO), so retraining is
always on ≤25,000 rows regardless of how many drift events have fired. This is a genuine
architectural change (not just a performance tweak): the classifier's memory of old data is now
bounded and approximate rather than exact and unbounded, which is the right tradeoff for a
long-running online system and also directly resolves the eval-cost concern above (Stage 7
dropped from 4,199s pre-fix / ~70min to 654s / ~11min per seed). Update latency measured at
~2.5-3.7s per drift event, down from ~150s, at a flat ~5.4GB memory footprint (previously
unbounded growth). Re-ran `run_stage7(n_seeds=1)` with the leakage fix AND the new classifier:
closed-loop final macro-F1 0.1738 vs. baseline 0.0288 (~6.03x), all 18 unit tests passing. This
is now a valid (if still single-seed) result — see `METRICS_HISTORY.md` for the full entry.

**Paper**: `paper/main.tex` (new, IEEE conference format) documents the architecture, the
leakage bug and fix as a methodological contribution in its own right, and the corrected Stage 7
result. `paper/figures/` holds three real, data-backed figures generated by
`paper/generate_figures.py`. `docs/PAPER_EVIDENCE_MAP.md` traces every number in the paper to
its source file.

## Current open items

See `STATUS.md` — kept current there instead of duplicated here, so there's exactly one place
that can go stale instead of two disagreeing ones.
