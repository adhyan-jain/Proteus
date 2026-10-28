# Proteus: Architecture

## Data flow

```
traffic ──> RandomForest ──> max-prob confidence ──> KS test vs reference ──(drift)──┐
                                                                                    v
   hot-swap <── release bundle <── validation gate <── BoundedBufferClassifier <── MMD gate <── WGAN-GP
```

| Stage | Module | Notes |
|---|---|---|
| Drift detector | `backend/drift.py` | `ks_2samp` on confidence; alpha 0.05 (loop), 0.01 (daemon) |
| Fidelity gate | `backend/fidelity.py` | Gaussian-kernel MMD, threshold 0.25, median-heuristic bandwidth |
| Generator | `backend/gan_full.py` | Conditional WGAN-GP, 3-layer G/critic (LayerNorm critic), GPU only; classes selected by "rare AND modelable" rules |
| Adaptive classifier | `backend/closed_loop_full.py` | `BoundedBufferClassifier` (20k reference reservoir + 5k recent), `ClosedLoopOrchestrator`; fixed 30% eval/fit split per window so scores are on rows never trained on |
| Runtime lifecycle | `backend/drift_daemon.py` | Ring buffer, KS monitor, off-path adaptation, validation gate, release packaging, hot-swap, canary + rollback |
| Releases | `backend/release_manager.py`, `model_manager.py` | SHA-256 manifests under `models/releases/vNNN`, double-buffered in-memory swap |
| API | `api/server.py` | `/predict`, hot-swap/rollback, telemetry; serves `results/results.pkl` and `api/cache/datasets_summary.json` |
| Console | `frontend/` | Next.js 16 / TypeScript / Tailwind; 10 screens; explicit "not available" states, no fabricated numbers |
| SDN | `sdn/` | Ryu 4.34 app (`ryu_ids_app.py`), Mininet topology, `feature_mapper.py` (OpenFlow flow stats -> unified schema) |

## Two backends

- **Demo** (`data`, `baseline`, `gan`, `stream`, `pipeline` + `app.py`, `run_pipeline.py`): small, CPU-friendly,
  runs in minutes; uses NSL-KDD if reachable, else a labelled synthetic NSL-KDD-schema set. Drives the
  Streamlit demo and the default release `v001`. Frozen unless a change breaks it.
- **Full scale** (`data_full`, `baseline_full`, `gan_full`, `closed_loop_full`, `evaluate_full`,
  `validate_full`): real CICIDS2017 (WTMC-2021 corrected, 2,100,021 rows, 25 classes, 80 features) and
  InSDN (343,889 rows, 8 classes) in one schema, stratified 70/15/15 splits. Sources and hashes:
  `data/MANIFEST.md`. No synthetic fallback here.

## Environments

- `.venv` (Python 3.12): main backend, API, tests. CUDA torch required (`torch==2.11.0+cu128`; a `+cpu`
  wheel is wrong). Install with `uv pip install`, never `uv pip sync`.
- `.venv-ryu` (Python 3.8): Ryu only; rebuild with `sdn/setup_ryu_venv.sh`.
- `frontend/node_modules`: Next.js app.

`backend/config.py` must be the first import in any module doing numeric work: it caps BLAS/OpenMP
threads before numpy/torch/sklearn initialise (otherwise 4 joblib workers x 16 BLAS threads each).

## Known limits (verified against the code, 2026-10-17)

1. **Stale drift reference (bug).** The KS reference is set once (daemon: first 30 live confidences;
   loop: initial model on its own first 50k training rows) and never recomputed when the model is
   adapted or hot-swapped. The adapted model, trained on a 25k buffer, is slightly less confident, so on
   unchanged traffic it alarms in 56% (loop, alpha 0.05) to 100% (daemon, alpha 0.01) of windows
   (10 seeds), versus 0% for an equal-size retrain. A reference recomputed for the serving model on a
   held-out sample gives ~0%. Fix: recompute the reference per model version at swap
   (`LiveSampleBuffer.set_reference_confidence` already exists and is unused).
2. **Daemon retrains on its own predictions** (`LiveSampleBuffer` stores predicted labels) plus
   zero-vector class-representative rows.
3. **Validation gate is vacuous in the daemon:** `CandidateValidationGate()` is created without
   validation data, so only shape/NaN sanity checks run.
4. **Canary cannot see degradation:** it counts errors only for inference exceptions or confidence < 0.10,
   which is unreachable for a 5-class model (max probability >= 0.2).
5. **Default release `v001` is a 5-class NSL-KDD-schema reference model** trained on synthetic data;
   the 25-class CICIDS2017 pipeline is offline.
6. **Closed-loop gains are not evidence that synthetic data helps** (see README research summary).
7. **No live SDN run:** Mininet needs root, so `LiveMininetSource` is unimplemented and the
   `sdn/topology/smoke_test.sh` / `scripts/run_real_sdn_e2e.sh` harnesses are written but unverified here.
8. **Telemetry:** only about 9 distinct numeric features can be populated from OpenFlow 1.3 counters
   (`feature_mapper.py`); the rest are explicitly absent, never fabricated.
