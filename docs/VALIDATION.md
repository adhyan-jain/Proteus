# Validation — what was actually executed (2026-09-17 audit session)

Every line below is a command that was actually run in this session and its actual outcome. See
`docs/END_TO_END_VALIDATION.md` for the acceptance checklist this feeds into.

| # | Command | Outcome |
|---|---|---|
| 1 | `python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"` | `2.11.0+cu128 True 12.8` |
| 2 | `free -h` (repeated at multiple points) | 12/15Gi RAM used, 17/22Gi swap used, 217-473Mi free — critical, pre-existing, unrelated to this session |
| 3 | `find . -iname "test_*.py"` | Only `sdn/topology/test_feature_mapper.py` existed pre-session |
| 4 | `python -m pyflakes proteus/ api/ run_pipeline.py run_stage7_5seed.py` | 9 findings; 4 real (dead imports/var), 5 false positives (intentional side-effect `proteus.config` imports, all `# noqa: F401`-marked in source) |
| 5 | `uv pip install --python .venv/bin/python pytest pyflakes` (TMPDIR redirected per CLAUDE.md rule 9) | Installed cleanly, `.venv` untouched otherwise |
| 6 | `pytest tests/ -q` | **14 passed** (`test_fidelity.py` x6, `test_drift.py` x4, `test_closed_loop_leakage.py` x4) |
| 7 | `python -m py_compile` on every edited file | All compiled cleanly |
| 8 | `python -c "from proteus.pipeline import run_pipeline; r = run_pipeline(); ..."` | Completed in <180s. `data_source: synthetic-fallback`, baseline macro-F1 0.982, 16 timesteps, 3 retrain events, 0 static-augmentation errors, all 3 conditions produced consistent, non-crashing macro-F1 series after the leakage fix |
| 9 | `torch.load('checkpoints/gan_full/epoch_80.pt', ...)` | Confirmed a real, existing 80-epoch WGAN-GP checkpoint (80 features, 12 class labels) — checkpoint infrastructure genuinely exists, was not fabricated |
| 10 | `git log --oneline -30`, `git status`, `git diff --stat` | Clean starting tree, 26 prior commits ahead of origin at session start (already pushed by user) |

## What this validates

- GPU/CUDA claim: **real**, directly confirmed, not assumed.
- Demo pipeline (`app.py` + `proteus/{data,baseline,gan,drift,fidelity,stream,pipeline}.py`):
  **genuinely runs end-to-end**, post-fix, with the synthetic-fallback data path (no network
  download attempted in this pass).
- `fidelity.py` and `drift.py`: **mechanism-level correctness independently verified** by new
  unit tests exercising real math (MMD on known-identical vs. known-different distributions;
  KS-test drift/no-drift on constructed distributions) — not just "the code runs," but "the
  code produces the mathematically expected answer."
- The leakage fix: **verified structurally** (disjoint partitions, correct fraction, reproducible
  given a fixed RNG state) via direct unit tests of the extracted `split_eval_fit` static method.
  It was **not** re-verified by a full Stage 7 rerun in this session (see
  `docs/KNOWN_LIMITATIONS.md` #1 for why and the exact command to do so).

## What this does NOT validate (explicitly, so it isn't assumed)

- The full-scale (`_full.py`) data pipeline, baseline, GAN, or Stage 3/4/7 numbers were **not
  re-executed** this session — those numbers in `METRICS_HISTORY.md` predate this session and
  are cited as prior evidence, not re-verified here, **except** for the Stage 7 closed-loop
  number, which this session determined to be invalid (see above and
  `docs/KNOWN_LIMITATIONS.md` #1).
- Live Mininet/Ryu was not touched — no root access.
- The Streamlit/Next.js UIs were not launched or browser-tested in this session (not required by
  the leakage fix, and starting two more Node/Python dev servers under the memory conditions
  observed above was judged an unnecessary additional risk to the shared machine this session).
