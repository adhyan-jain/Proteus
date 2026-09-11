# Proteus — Current Status (read this first)

**This file is the handoff point.** If you are a new agent session — Claude Code, Antigravity,
Cursor, or anything else — picking this project up cold, read this file before anything else.
It tells you exactly what's running, what's done, what's blocked, and what to do next. Read
`CLAUDE.md`/`AGENTS.md` next for the operating rules (both say the same things — read whichever
your tool honors), then `ARCHITECTURE.md` for the system shape, `CHANGELOG.md` for how it got
here, and `METRICS_HISTORY.md` for every real number any run has produced.

**Standing rule**: update this file at the end of every real work session — not after every
commit, but whenever you stop, hand off, or finish a stage. A stale STATUS.md defeats the point.

Last updated: 2026-09-11, by a Claude Code session.

## What's running right now

If these are still running when you pick this up (check first, don't assume — a session restart
or reboot since this was written would have stopped them):

```bash
# Streamlit demo UI                 — http://localhost:8501
.venv/bin/streamlit run app.py --server.headless true --server.port 8501

# Proteus API (serves results.pkl + dataset summaries as JSON for the Next.js UI)
.venv/bin/uvicorn api.server:app --port 8000    # http://localhost:8000

# Next.js mission-control UI        — http://localhost:3000
cd frontend && npm run dev
```
Check with `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:PORT` — if any return
`000`, that server isn't up; restart with the commands above.

## What's done (verified, real, committed)

- **Demo POC**: end-to-end, working, frozen per standing instruction. `app.py` +
  `proteus/{data,baseline,gan,drift,fidelity,stream,pipeline}.py`. Numbers in
  `METRICS_HISTORY.md`'s first entry.
- **Stage 1 (full-scale data)**: CICIDS2017 (WTMC-2021 corrected, from DistriNet/KU Leuven) +
  InSDN (from UCD ASEADOS Lab, the authors' own institution) — both verified-source, hashed in
  `data/MANIFEST.md`. Unified schema in `proteus/data_full.py`.
- **Stage 3 (WGAN-GP, full scale)**: trained on GPU, 80 epochs, real diversity diagnostics.
  **0/12 classes mode-collapsed; 3/12 classes flagged over-dispersed** (see next section — this
  needs a decision, not yet made). Numbers in `METRICS_HISTORY.md`.
- **Next.js mission-control UI**: 10 screens, real-data-or-explicit-empty-state, QA'd with
  Playwright (locally installed npm package — no Playwright MCP existed in this installation
  at the time; check again now, see "Tooling notes" below).
- **Overview page pipeline diagram click-to-describe**: each of the 8 stage cards in the
  closed-loop pipeline diagram (`frontend/src/components/pipeline/pipeline-diagram.tsx`) is now
  clickable and shows a short plain-language explanation of that stage — a real request from
  earlier in the project that had never been implemented (no `onClick` existed anywhere in
  `frontend/src` before this). Verified with a local Playwright script against the running dev
  server and `npm run build`.
- **Ryu 4.34 controller**: working in `.venv-ryu` (Python 3.8), reproducible via
  `sdn/setup_ryu_venv.sh`. Verified with `ryu-manager --version` and a successful
  `ryu.app.simple_switch_13` load.
- **GPU training confirmed working**: RTX 4060 via CUDA-build torch
  (`torch==2.11.0+cu128`, NOT the `+cpu` build — see `CLAUDE.md` rule 1 for why this matters and
  how to check). Verified with a real GPU matmul, not just `torch.cuda.is_available()`.

## Blocked — needs the repo owner, not an agent

- **Mininet is not installed.** `mn --version` fails. Needs `sudo pacman -S mininet` or an AUR
  helper (`yay -S mininet` / `paru -S mininet`), run interactively by the repo owner — an agent
  cannot supply a sudo password, and Mininet needs root at *runtime* too, not just at install
  time, so this isn't a one-time hurdle to work around. This blocks Stage 0's smoke test and
  everything in Stages 5-7 that needs a live Mininet/Ryu deployment (see `ARCHITECTURE.md` /
  the original project brief for stage numbering).

## Needs a decision — don't silently resolve either way

- **3 WGAN-GP target classes are over-dispersed** (`Bot - Attempted` ~3160x, `DoS slowloris -
  Attempted` ~11x, `FTP-Patator` ~3.2x borderline — see `METRICS_HISTORY.md`'s Stage 3 entry).
  Options: (a) accept as a documented limitation and proceed to Stage 4, (b) retrain with more
  epochs / a different learning rate, (c) exclude these 3 from GAN augmentation like the
  already-excluded too-rare classes. Not yet decided as of this writing — ask the repo owner
  before picking one.

## Not yet built

Stage 3's baseline + static-augmentation comparison classifiers at full scale; Stage 4 (drift
detector + fidelity gate validated at real scale — blocked behind the decision above); Stages
5-7 (live Mininet deployment, closed-loop orchestration, 5-seed statistical evaluation — blocked
on the Mininet install above); the final `RESULTS_SUMMARY.md` deliverable.

## Tooling notes for a different agent/IDE

- This repo was developed primarily with Claude Code. If you're a different tool: the
  `AGENTS.md` file (not `CLAUDE.md`) is the convention-neutral one — same rules, tool-agnostic.
- Git remote is configured (`origin` → `git@github.com:adhyan-jain/Proteus.git`) and has been
  pushed to before. **Never push without the repo owner's explicit go-ahead in the moment** —
  this has been treated as a hard rule throughout, not a one-time approval.
- **No `Co-Authored-By` or AI-attribution trailers in any commit, ever** — check your tool's
  default commit-message behavior and suppress it if needed.
- Three separate Python environments exist for real, documented reasons — see `CLAUDE.md`'s
  environment-discipline rule before assuming you can consolidate them: `.venv` (3.12, main
  backend + API), `.venv-ryu` (3.8, SDN controller only), plus `frontend/node_modules` (Node).
- `/tmp` on this machine is a small RAM-backed tmpfs with a user quota — large package installs
  need `TMPDIR` redirected to a disk-backed path (see `CLAUDE.md` rule 9) or they'll fail with a
  confusing "Disk quota exceeded" error, or contribute to OOM risk.
- This machine runs a lot of unrelated software (other dev servers, browser, IDE) and has
  chronically tight RAM (16GB) — expect real memory pressure, don't assume a clean, idle
  machine. Check `free -h` before launching anything memory-heavy.
- A `everything-claude-code` plugin marketplace (`ecc`) plus `frontend-design`, `playwright`,
  `code-review`, `skill-creator`, and `commit-commands` plugins were added to this Claude Code
  installation's settings partway through development but were not live in the session that
  added them (plugins load at session start). If you're a fresh Claude Code session, they should
  be available now — check before assuming they aren't, and before assuming a workaround (like
  a locally-installed npm Playwright) is still necessary.
