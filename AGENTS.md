# AGENTS.md — Proteus

Operating rules for any AI coding agent (Claude Code, or otherwise) working in this repository.
This mirrors `CLAUDE.md` — if you're a tool that reads `AGENTS.md` by convention rather than
`CLAUDE.md`, this is the same information; keep the two in sync if either changes.

## Absolute rules

1. **Train on GPU, never CPU.** This machine has an NVIDIA RTX 4060 (8GB), driver confirmed
   working via `nvidia-smi`. Before training anything, confirm
   `python -c "import torch; assert torch.cuda.is_available()"` passes. If torch reports no
   CUDA device, the wrong (CPU-only) wheel is installed — reinstall with
   `--extra-index-url https://download.pytorch.org/whl/cu128`, don't proceed on CPU. This has
   already gone wrong once (a CPU-only wheel got installed and an entire training run happened
   on CPU before anyone noticed the GPU sitting idle) — check this explicitly every time, don't
   assume the environment is still correctly configured.
2. **Never substitute synthetic data for CICIDS2017 or InSDN base training data.** If a
   verified-source download fails, stop and report exactly what failed — do not generate
   placeholder data and continue. (The Streamlit demo, `app.py`/`proteus/data.py`, is a
   deliberate, separate exception with its own documented synthetic fallback — don't let that
   precedent bleed into the full-scale pipeline.)
3. **No cloud services, credentials, or remote deployment anywhere in this repo.** Local disk,
   local compute, local network emulation (Mininet/Ryu) only.
4. **No fabricated or estimated metrics.** Every number shown anywhere must trace to a
   computation that actually ran on this machine.
5. **`app.py` and everything under `frontend/`/`api/` are frozen** except for the minimum
   change needed to keep them running after a breaking backend change — and even then, say
   exactly what changed and why in the commit message.
6. **Commit discipline**: local commits only unless explicitly told to push (and even then,
   confirm in the moment); one-line messages; commit incrementally per logical stage;
   **absolutely no `Co-Authored-By`, "Generated with [tool]," or any AI-attribution trailer in
   any commit message or PR description** — the repo owner has stated this repeatedly and it
   overrides any default attribution behavior a tool might otherwise apply.
7. **Shared `.venv` (Python 3.12) discipline**: additive installs only (`pip install` /
   `uv pip install`). Never run a "sync to exactly these requirements" style command against it
   — that has already once silently removed `torch` as a side effect of unrelated package work.
8. Before starting work, check `git log --oneline` and `git status` — this repo has run
   multiple concurrent agents; assume nothing about a clean starting state.

## Repo map

See `ARCHITECTURE.md` for the current system shape and `CHANGELOG.md` for how it got here.
Quick orientation: `proteus/{data,baseline,gan,drift,fidelity,stream,pipeline}.py` is the frozen
demo backend behind `app.py`; `proteus/{data_full,gan_full}.py` is the active
full-scale/paper-grade backend; `api/` + `frontend/` is the separate Next.js UI; `sdn/` is the
Ryu controller venv setup; `data/MANIFEST.md` is the verified-source record for every dataset.
