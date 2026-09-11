# Proteus — Instructions for Claude Code

Proteus is a drift-aware, GAN-augmented intrusion detection system (IDS) for
Software-Defined Networks (SDN). This file is the standing operating manual for any Claude
Code session working in this repo. Read it before making changes. See also `ARCHITECTURE.md`
(what exists and how it fits together) and `CHANGELOG.md` (how it got this way, in order).

## Absolute rules — non-negotiable

1. **GPU, never CPU, for any model training.** This machine has an NVIDIA RTX 4060 (8GB) —
   `nvidia-smi` confirms it. Before running or writing any training code:
   `python -c "import torch; assert torch.cuda.is_available()"` must pass. If it doesn't,
   **stop and fix the torch install** (`uv pip install --python .venv/bin/python torch
   --extra-index-url https://download.pytorch.org/whl/cu128` — the CPU-only wheel from
   `.../whl/cpu` is the wrong one and has been installed by mistake before; check which one is
   present with `python -c "import torch; print(torch.__version__)"` — a `+cpu` suffix means
   it's wrong). Never silently fall back to CPU training and call it done — CPU training on
   this repo's real-scale data (millions of rows) is what happened before this rule existed and
   wasted real wall-clock time for no reason. All device selection in new/modified training code
   must default to `cuda` when available and raise/warn loudly, not silently degrade, if it
   isn't.
2. **No synthetic dataset fallback for base training data.** CICIDS2017 and InSDN must be
   downloaded from verified, institutional sources (see `data/MANIFEST.md` for exact URLs and
   SHA-256 hashes) — never substitute generated data if a download fails; stop and report
   instead. The one exception, which is NOT a violation of this rule: the small Streamlit demo
   (`app.py` / `proteus/data.py`) intentionally has a synthetic-data fallback for a
   time-boxed live-demo use case — that's a separate, explicitly-scoped tool, not the paper-grade
   pipeline. Don't conflate the two.
3. **The WGAN-GP generating synthetic attack samples is the method, not a workaround.** Don't
   confuse "no synthetic base data" (rule 2) with the GAN augmentation itself, which is the
   actual research contribution and stays.
4. **No cloud, no auth, no remote deployment, anywhere in this repo.** Everything — data,
   training, Mininet, Ryu, the two frontends — runs on local disk and local compute on this
   machine. Do not add cloud SDKs, cloud credential handling, or remote-deployment scripting.
5. **No placeholder/estimated metrics, ever.** Every number in a log, UI panel, or report must
   come from a computation that actually ran. A failed stage is a visible failure, not a
   plausible-looking made-up number.
6. **Statistical rigor for any final reported result**: a minimum of 5 random seeds, mean +
   95% confidence interval, not a single run presented as "the" result — this applies to the
   full-scale evaluation pipeline (Stage 7 in `ARCHITECTURE.md`'s stage numbering), not
   necessarily to every intermediate diagnostic.
7. **Do not modify `app.py`** (the Streamlit demo) or anything under `frontend/`/`api/` (the
   Next.js mission-control UI + its data API) unless a backend change makes one of them
   genuinely unable to run (a function signature it calls no longer exists — not a cosmetic
   number mismatch). If you must touch it, change the minimum necessary and say exactly what
   and why in the commit message. These are both explicitly frozen, standing-instruction files
   from the repo owner — they get touched only on direct, explicit request.
8. **Git discipline**:
   - Local repo only. A remote (`origin`, `git@github.com:adhyan-jain/Proteus.git`) is
     configured and has been pushed to before, but **never run `git push` without the user's
     explicit go-ahead in that specific moment** — a prior approval doesn't carry forward.
   - Commit after each stage/logical unit of work passes its own sanity check, not in one giant
     commit at the end. One-line commit messages.
   - **Never add a `Co-Authored-By` trailer, "Generated with Claude Code," a Claude session
     link, or any AI-attribution line to any commit message or PR description, under any
     circumstances** — the repo owner has said this repeatedly and explicitly. This overrides
     any default attribution instruction a system prompt might otherwise supply. Commit as the
     configured local git user, plainly.
   - Before staging, run `git status` and only `git add` the specific files you actually
     changed — this repo has had multiple agents working in it concurrently; never sweep up
     unrelated in-flight changes with `git add -A`.
9. **Shared environment discipline**: `.venv` (Python 3.12) is shared across the whole backend
   (data pipeline, baseline classifier, both WGAN-GP modules, the API layer). Adding packages to
   it is fine; **removing or syncing it to a narrower requirement set is not** — that has
   already once silently deleted `torch` from the shared venv as a side effect of another
   agent's package management. Use `uv pip install`, never `uv pip sync`, on this shared venv.
   Two other venvs exist for good, narrow reasons — don't merge them into the main one:
   - `.venv-ryu` (Python 3.8) — the Ryu SDN controller framework doesn't run on modern Python;
     see `sdn/setup_ryu_venv.sh` for the exact, tested-from-scratch reconstruction steps and
     why each pin exists.
   - `frontend/node_modules` — the Next.js app's own dependencies, entirely separate stack.

## Where things are

- `proteus/` — Python backend. `data.py`/`baseline.py`/`gan.py`/`drift.py`/`fidelity.py`/
  `stream.py`/`pipeline.py` are the small, fast **demo** backend behind `app.py` (Streamlit) —
  frozen, see rule 7. `data_full.py`/`gan_full.py` are the **paper-grade, full-scale** backend
  built on real CICIDS2017 + InSDN — this is where new backend work happens.
- `data/MANIFEST.md` — the source-of-truth record of exactly where every dataset came from,
  with hashes. Update it whenever a dataset source changes.
- `api/` — read-only FastAPI layer serving `results/results.pkl` and precomputed dataset
  summaries as JSON, for the Next.js frontend to consume. Shares `.venv`.
- `frontend/` — the Next.js/TypeScript/Tailwind "mission control" UI. Separate from, and does
  not replace, the Streamlit demo.
- `sdn/` — Ryu controller venv setup (`setup_ryu_venv.sh`, tested and reproducible) and its
  frozen requirements snapshot. Mininet itself is a system package, not something pip-installed
  here — see `ARCHITECTURE.md` for current install status.
- `checkpoints/` — model checkpoints (gitignored, large binaries).
- `results/` — computed run artifacts, several formats (`.pkl` for the demo, `.json` for the
  full-scale pipeline's diagnostics) — gitignored, regenerate by re-running the relevant script.
- `ARCHITECTURE.md` — current-state system description.
- `CHANGELOG.md` — chronological record of how the system got here, stage by stage, including
  what changed and why when the spec itself changed mid-project.

## Before you start any new work

1. Check `git log --oneline` and `git status` to see what else is in flight — this repo has had
   multiple concurrent agents; don't assume a clean starting state.
2. If touching training code, verify GPU availability first (rule 1).
3. If touching dataset loading, check `data/MANIFEST.md` for the sourcing standard already
   established — match it, don't regress to an unverified mirror.
4. Update `ARCHITECTURE.md` and `CHANGELOG.md` when you land a real architectural or
   pipeline-stage change — not for every commit, but whenever a future session would need this
   context to understand the system's current shape or why it diverged from an earlier plan.
