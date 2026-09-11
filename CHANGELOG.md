# Proteus — Changelog / Evolution

Chronological record of how the pipeline got to its current shape, including where the plan
itself changed mid-project and why. This is a narrative log, not a commit-by-commit mirror —
see `git log` for that. Dates are when the work happened (this machine's local time).

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

## Open items as of this entry

- Full-scale WGAN-GP training: restarted on GPU, in progress at time of writing — see the most
  recent commit / `results/gan_full_diagnostics.json` (once it exists) for real outcomes.
- Stages 3 (baseline + static-augmentation comparison at full scale), 4 (drift detector +
  fidelity gate validated at real scale), 5-7 (live Mininet deployment, closed-loop
  orchestration, 5-seed statistical evaluation): not yet built. Stages 5-7 specifically blocked
  on Mininet installation (see above).
- `RESULTS_SUMMARY.md` (final deliverable comparing the three conditions with confidence
  intervals, honest comparison against the NetGuard reference point, and a list of any
  divergences from the originally-planned architecture): not yet written — depends on the above.
