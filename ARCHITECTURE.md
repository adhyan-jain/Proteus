# Proteus — Current Architecture

Snapshot of what exists right now and how it fits together. For current running state, blockers,
and pending decisions, see `STATUS.md` first. For how it got here, see `CHANGELOG.md`. For every
real metric any run has produced, over time, see `METRICS_HISTORY.md`. For operating rules, see
`CLAUDE.md`/`AGENTS.md`.

## The idea, in one paragraph

Proteus is an IDS (Intrusion Detection System) for SDN (Software-Defined Networks) that adapts
to evolving attack traffic instead of being trained once and frozen. A classifier watches live
traffic; a drift detector watches the classifier's own confidence for statistically significant
change; when drift fires, a WGAN-GP (Wasserstein GAN with Gradient Penalty) generator produces
synthetic examples of the new/rare attack pattern; a fidelity gate (MMD — Maximum Mean
Discrepancy) checks those synthetic samples against real recent traffic before admitting them
into a retraining set; the classifier retrains and redeploys. The novelty is the closed loop
running inside a live SDN controller with fidelity-gated admission as an explicit safety step —
not any single component in isolation (see the original project brief in memory/prior
conversation for the full novelty argument and prior-art comparison, not duplicated here).

## Two parallel backends — do not confuse them

### 1. Demo backend (`proteus/{data,baseline,gan,drift,fidelity,stream,pipeline}.py`, `app.py`)

A small, fast, self-contained proof-of-concept built to run end-to-end in minutes on a laptop
CPU. Uses NSL-KDD if reachable, else a synthetic NSL-KDD-schema dataset generated in code
(explicitly labeled as such in the UI). Small WGAN-GP (2 hidden layers, ~300 training steps).
Drives a Streamlit UI (`app.py`) with an architecture diagram, live metrics, a "run pipeline"
button, and a live drift-detector demo. **This is frozen** — a standing instruction from the
repo owner, since it's the thing actually demoed live. Touch it only for a genuinely
breaking-change fix, and say so explicitly.

Run: `.venv/bin/streamlit run app.py`

### 2. Full-scale / paper-grade backend (`proteus/{data_full,gan_full}.py`, and growing)

The real thing, built to the ground rules in `CLAUDE.md` (verified sources, no synthetic
fallback, GPU training, statistical rigor). Actively developed — this is where new backend
work happens.

- **`data_full.py`** — loads and unifies CICIDS2017 (WTMC-2021 corrected variant) and InSDN
  into one feature schema. See `data/MANIFEST.md` for exact sources/hashes.
  - CICIDS2017: 2,100,021 rows post-cleaning, 25 real label classes (long-tailed, BENIGN down to
    single-digit-count attack subclasses), 80 features, stratified 70/15/15 train/val/test.
  - InSDN: 343,889 rows, 8 classes, 80 features (same CICFlowMeter feature family, different
    column-naming convention — reconciled via a verified positional column mapping, see the
    module's `INSDN_TO_CICIDS2017_COLS`), stratified 70/15/15 split.
- **`gan_full.py`** — full-depth conditional WGAN-GP (3-layer generator/critic, LayerNorm in
  the critic per standard WGAN-GP guidance against BatchNorm), trained on CICIDS2017's real
  class imbalance. GAN-target classes are selected by two explicit, documented criteria (rare
  AND modelable — see the module docstring for the exact thresholds and reasoning); classes too
  rare to model meaningfully are excluded, not faked. Real convergence criterion (generator-loss
  plateau detection over a rolling window), not a fixed step/epoch count. Checkpointed every
  epoch (keeps the 3 most recent). Real per-class diversity/mode-collapse diagnostics comparing
  generated samples against held-out real validation samples, written to
  `results/gan_full_diagnostics.json`.
  - **Must run on GPU** (RTX 4060, confirmed present) — see `CLAUDE.md` rule 1. A CPU-only
    torch wheel has been mistakenly installed before; always verify
    `torch.cuda.is_available()` before launching a training run.

Not yet built at full scale (as of this writing): the full baseline/static-augmentation
comparison classifiers, the production-scale drift detector and fidelity gate validation, the
live Mininet/Ryu deployment, the closed-loop orchestration, and the 5-seed statistical
evaluation — these are the remaining stages of the paper-grade scale-up (see `CHANGELOG.md`'s
most recent entries for exact status and open blockers).

## SDN controller stack (`sdn/`)

Ryu 4.34 (the SDN controller framework specified in the original project brief) runs in a
**dedicated Python 3.8 virtualenv** (`.venv-ryu`), because upstream Ryu hasn't been updated
since ~2019 and doesn't run on this machine's system Python or the main `.venv` (3.12/3.14).
`sdn/setup_ryu_venv.sh` reproduces the working environment from scratch — it pins a specific,
verified combination (old `setuptools`, `--no-build-isolation`, an exact `eventlet`+`dnspython`
pair, and a small hand-written `oslo.config` compatibility shim) found by actually hitting and
fixing each real incompatibility, not by guesswork. Verified via `ryu-manager --version` and a
successful load of `ryu.app.simple_switch_13`.

**Mininet is not yet installed** on this machine — it needs `sudo pacman -S mininet` or an AUR
helper (`yay -S mininet`), which requires the repo owner's own interactive sudo session (an
agent cannot supply this). Until it's installed, Stage 0's smoke test (bring up a trivial
Mininet topology + confirm the controller attaches) cannot run, which blocks every
live-deployment stage downstream of it.

## Two frontends

### Streamlit demo (`app.py`) — see "Demo backend" above. Frozen.

### Next.js mission-control UI (`frontend/` + `api/`)

A separate, from-scratch "SOC console"-styled dashboard, built after the demo, sitting next to
it rather than replacing it. Screens: Overview (hero closed-loop pipeline diagram), Live
Detection, Topology (explicit "no live controller connected" state — see Mininet status above),
Drift Monitor, Synthetic Lab, Fidelity Gate, Adaptation, Experiments, Audit Log, Models.
Next.js 16 + TypeScript + Tailwind v4, hand-rolled design system (no shadcn CLI dependency),
Recharts for charts. Backed by `api/server.py`, a read-only FastAPI layer over
`results/results.pkl` (the demo's run output) and a precomputed summary of the full-scale
datasets (`api/precompute_datasets.py` → `api/cache/datasets_summary.json`). No fabricated
numbers anywhere — explicit "not available" states for anything the backend doesn't compute yet
(inference latency, controller CPU, confidence intervals, diversity diagnostics at the time it
was built).

Run:
```
.venv/bin/uvicorn api.server:app --port 8000      # API, from repo root
cd frontend && npm run dev                         # UI, http://localhost:3000
```

## Environments

- `.venv` (Python 3.12) — shared main backend environment: pandas/numpy/scikit-learn/torch
  (must be the CUDA build, not `+cpu` — see `CLAUDE.md` rule 1)/FastAPI/uvicorn/kaggle CLI.
  Additive installs only — see the shared-venv discipline rule in `CLAUDE.md`.
- `.venv-ryu` (Python 3.8) — Ryu controller stack only. See `sdn/setup_ryu_venv.sh`.
- `frontend/node_modules` — Next.js app dependencies.

## Data provenance

Both real datasets are sourced from the original authors'/publishers' own institutional pages,
not third-party re-uploads — see `data/MANIFEST.md` for exact URLs, SHA-256 hashes, and
retrieval dates:
- **CICIDS2017 (WTMC-2021 corrected)** — DistriNet Research Group, KU Leuven (the correcting
  paper's own authors' institution).
- **InSDN** — UCD ASEADOS Lab, University College Dublin (the original dataset paper's authors'
  own institution). An earlier version of this pipeline used a Kaggle community re-upload before
  the official source was located and switched to.
