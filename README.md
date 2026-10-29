# Proteus: Drift-Aware, GAN-Augmented Intrusion Detection for SDN

Proteus is an adaptive intrusion-detection system for Software-Defined Networks. A Random Forest
classifier scores flows; a two-sample Kolmogorov-Smirnov (KS) test on the classifier's prediction
confidence flags drift; on drift, a conditional WGAN-GP proposes synthetic samples of the affected
classes, a Maximum Mean Discrepancy (MMD) fidelity gate filters them, and a bounded-memory
classifier (`BoundedBufferClassifier`, 20,000-row reference reservoir + 5,000-row recent buffer) is
refit. An autonomous daemon packages candidates as hashed release bundles, hot-swaps them in memory,
and rolls back on canary failure. A FastAPI service exposes inference and telemetry to a Next.js
console; a Ryu controller app feeds OpenFlow flow statistics.

```
traffic -> Random Forest -> confidence -> KS drift test -> (drift) -> WGAN-GP -> MMD gate
                                                                          |
                           hot-swap release <- validate <- BoundedBufferClassifier refit
```

## Status

Working engineering prototype, not a validated product. Read **Known limits** in
[`ARCHITECTURE.md`](ARCHITECTURE.md) before relying on any behaviour; the first item is a real bug
(the drift reference is never recomputed after the model is adapted).

## Quick start

```bash
# GPU check (training must use CUDA; see CLAUDE.md)
.venv/bin/python -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"

.venv/bin/pytest tests -q                                   # test suite
.venv-ryu/bin/python -m unittest discover -s sdn/topology -p "test_*.py"   # Ryu-side tests

.venv/bin/python run_pipeline.py                            # small demo pipeline (writes results/results.pkl)
.venv/bin/streamlit run app.py --server.headless true --server.port 8501    # Streamlit demo

.venv/bin/uvicorn api.server:app --port 8000                # API
cd frontend && npm run dev -- -p 3300                       # console
```

Containers, release bundles and the API reference: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
Dataset sources and SHA-256 hashes: [`data/MANIFEST.md`](data/MANIFEST.md).

## Layout

| Path | Contents |
|---|---|
| `backend/` | Backend: demo (`data`, `baseline`, `gan`, `stream`, `pipeline`), full scale (`data_full`, `baseline_full`, `gan_full`, `closed_loop_full`, `evaluate_full`, `validate_full`), runtime (`drift_daemon`, `model_manager`, `release_manager`), shared (`drift`, `fidelity`, `config`) |
| `api/` | Read-only FastAPI layer + inference/hot-swap endpoints |
| `frontend/` | Next.js site: `src/app/new/` study pages (overview, novelty, gap, forwarding, validity, pipeline, faq, reproduce, literature) and `src/app/old/` console (11 pages); `/` redirects to `/new` |
| `sdn/` | Ryu app, Mininet topology, OpenFlow-to-schema feature mapper |
| `models/` | Versioned release bundles |
| `research/insdn_controller/` | Current study: controller-observable telemetry in InSDN (paper, `ofgap/` analysis, `live/` Ryu/Mininet captures, `results/`, `reproduce.sh`). Own README: `research/insdn_controller/README.md` |
| `tests/`, `scripts/` | Tests; deployment-artifact export, rollback, real-SDN E2E harness |
| `docs/`, `data/` | `docs/DEPLOYMENT.md` (containers, release bundles, API reference); `data/MANIFEST.md` (dataset sources and hashes; raw data under `data/raw/` is local and not in git) |

## What the research found (short version)

Several pre-registered studies tested whether the GAN/synthetic-data idea actually helps. The
honest summary is that it does not, and the useful by-products are engineering lessons:

- **The original "5.91x macro-F1" headline is superseded.** The demo's gain over baseline comes from
  oracle labels on most of every window, not from synthetic data. Do not cite it.
- **Synthetic-dose controller (P0/P1, preregistered):** indistinguishable from plain real-only
  adaptation (recovery difference 0.000 [0.000, 0.000], 10 seeds); the binding constraint was the
  promotion gate's ability to certify candidates, not candidate quality.
- **More historical evidence in the promotion gate (v1.5, 20 seeds):** a narrow recovery gain
  (+0.155 [0.023, 0.288]) with one safety breach in one seed; no new algorithm claimed.
- **Class-aware bounded replay:** no reliable F1 gain over plain bounded replay (paired +0.004
  +/-0.011), but it keeps historical detection (0.84 vs 0.60). Under corrupted update labels, class
  quotas are themselves a vulnerability; a class-balanced historical reference gave a robust ~+0.24
  retention gain. Pre-declared verdict for the proposed method: NO-GO (8 of 10 criteria).
- **Telemetry contract:** only 9 numeric features are physically observable from OpenFlow 1.3
  counters, so a model must be trained on features the controller can actually supply. On 30k
  CICIDS2017 test flows, a 9-feature model reached 97.55% recall while a zero-filled 77-feature
  model reached 0.00%.
- **Drift alarm after adaptation (driftref):** with a stale reference, the system's own adapted model
  alarms on unchanged traffic in 56% (loop) to 100% (daemon) of windows, versus 0% for an
  equal-size retrain; recomputing the reference per model version removes it. The principle is
  known practice, so no novelty is claimed; the bug is real and unfixed.
- **Publishability audits (2026-10-10):** none of the above is a new-method contribution; the only
  possibly publishable artefact is the leakage-controlled replay harness as research software.

The older research programme's full dossiers, preregistrations, raw results and papers were archived
outside the repository (`~/private_research/proteus_repo_snapshot_20261017.tar.gz`, SHA-256
`af54da7b119085d290ac67b99c9a5f946e4acfc1b4bd526ec1373e426cf66a6c`) and removed from the tree.
Numbers above come from stored result files in that archive, not estimates.

The current study is separate from that programme. It examines what an SDN controller can observe
from OpenFlow traffic (InSDN ONOS captures, plus Mininet/Ryu captures recorded on this machine) and lives
in [`research/insdn_controller/`](research/insdn_controller/README.md), with its own paper, `reproduce.sh`
and result files in `research/insdn_controller/results/`. Its numbers are cited there, not here.
