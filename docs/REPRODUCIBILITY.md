# Proteus — Academic Reproducibility & Research Guide

This document provides exact, end-to-end instructions for reproducing all quantitative claims, evaluation pipelines, synthetic diagnostics, and publication figures in **Proteus**.

---

## 1. Environment & Hardware Verification

### Prerequisites & Dependencies
- **OS**: Linux (tested on Linux x86_64)
- **Python**: 3.12 for main research pipeline (`.venv`), Python 3.8 for SDN controller (`.venv-ryu`)
- **GPU**: NVIDIA RTX 4060 (8GB VRAM) or equivalent CUDA-capable GPU

### Verify PyTorch CUDA Environment
Before running any experiment, confirm that PyTorch is using the GPU:
```bash
cd /home/adhyan/Desktop/Proteus
.venv/bin/python -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable!'; print('GPU:', torch.cuda.get_device_name(0))"
```
*Note*: If PyTorch reports CPU-only, reinstall PyTorch with CUDA 12.8 support:
```bash
TMPDIR=/home/adhyan/Desktop/Proteus/.uv-tmp .venv/bin/pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cu128
```

---

## 2. Dataset Provenance & Clean Verification

Datasets are recorded with SHA-256 hashes in `data/MANIFEST.md`:
- **CICIDS2017**: WTMC-2021-corrected version from DistriNet / KU Leuven (`data/cicids2017/`)
- **InSDN**: SDN-native intrusion dataset from UCD ASEADOS Lab (`data/insdn/`)

Verify data hashes:
```bash
sha256sum data/cicids2017/*.csv
```

---

## 3. Unit Test Suite Verification

Run all automated unit tests across pipeline components, non-leakage invariants, drift detection, MMD fidelity gating, and feature mapping:

```bash
# Core pipeline & non-leakage tests
.venv/bin/pytest tests/ -v

# SDN Feature Mapper unit tests
.venv/bin/python -m unittest discover -s sdn/topology -p "test_*.py" -v
```

---

## 4. Demo Pipeline Execution

Run the lightweight demo pipeline and generate `results/results.pkl`:
```bash
.venv/bin/python run_pipeline.py
```
To launch the interactive Streamlit demo UI:
```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8501
```

---

## 5. Full-Scale Stage 7 Evaluation & Multi-Seed Sweep

### Single-Seed Evaluation ($n=1$)
To run the full-scale Stage 7 evaluation (Baseline vs. Static Augmentation vs. Closed-Loop `BoundedBufferClassifier`):
```bash
.venv/bin/python -c "from proteus.evaluate_full import run_stage7; run_stage7(n_seeds=1)"
```

### Multi-Seed Evaluation Sweep ($n=5$)
To execute the multi-seed sweep and compute 95% confidence intervals:
```bash
.venv/bin/python run_stage7_5seed.py
```
Output artifacts are saved to `results/stage7_evaluation.json` and `results/stage7_per_class_f1.json`.

---

## 6. Buffer Capacity Sensitivity Analysis

Execute the buffer capacity sweep across Small (10k/2.5k), Default (20k/5k), and Large (40k/10k) configurations:
```bash
.venv/bin/python scratch/test_buffer_sensitivity.py
```
Output artifact is saved to `results/buffer_sensitivity.json`.

---

## 7. Publication Figures & Paper Compilation

### Generate Figures
To update all publication figures from real result artifacts:
```bash
.venv/bin/python paper/generate_figures.py
```
Generated PNGs are saved to `paper/figures/`.

### Compile LaTeX Paper
```bash
cd paper/
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

---

## 8. Live SDN / Mininet Integration

### Ryu Controller Launch (Non-Root)
```bash
.venv-ryu/bin/ryu-manager sdn/topology/ryu_ids_app.py --verbose
```

### Mininet Emulation Smoke Test (Requires Root)
```bash
sudo bash sdn/topology/smoke_test.sh
```
*Expected Output*: `SMOKE TEST PASSED` in stdout and switch connectivity logs in `/tmp/proteus_ryu_smoke.log`.

---

## 9. Claim Tracing & Evidence Map

For a detailed claim-by-claim mapping between paper statements and underlying execution artifacts, refer to `docs/PAPER_EVIDENCE_MAP.md`.

## 6. Intervention research line (P0 → P1 → S2 gate; SPEC v1.3/v1.4)

Everything here is CPU (scikit-learn random forests); the GPU rule applies to the WGAN-GP stage (P2), which was **not run** because its gate
(H2 ∧ H3a ∧ H3b) did not open. All commands from the repo root with `.venv`; memory guard: the cache load needs ≳ 2.5 GiB free.

```bash
# 0. one-time: verified CICIDS2017 arrays + group hashes (results/cache/, gitignored)
.venv/bin/python -m proteus.intervention.cache build
# 1. frozen P0 (S1; ~6 min)           -> results/intervention_p0_S1_{B25,B100,summary}.json
.venv/bin/python -m proteus.intervention.p0
# 2. preregistered P1 (10 seeds x 23 arms, ~2 h)  -> results/p1/intervention_p1_S1_B100_seed*.json
PYTHONUNBUFFERED=1 .venv/bin/python -u -m proteus.intervention.p1 --out-dir results/p1
# 3. analysis (deterministic; ~1 min) -> results/intervention_p1_S1_B100_{summary,decisions}.json
.venv/bin/python -m proteus.intervention.analyze_p1 --in-dir results/p1
# 4. the P3 gate (S2; ~3 min)         -> results/intervention_p0_S2_*.json
.venv/bin/python -m proteus.intervention.p0_s2
# 5. audits                            -> results/p1_leakage_audit.json, results/p1_audit_sensitivity.json
.venv/bin/python scripts/audit_p1_leakage.py && .venv/bin/python scripts/audit_p1_sensitivity.py
# 6. paper (figures/tables/number macros are generated from the artifacts)
.venv/bin/python paper/p1/make_assets.py && (cd paper/p1 && latexmk -pdf main.tex)
# 7. verification record + console
.venv/bin/python scripts/write_verification_report.py
.venv/bin/uvicorn api.server:app --port 8000      # then: cd frontend && npm run build && npx next start -p 3300
```

Determinism: every random stream is derived from (seed, window, purpose[, class]); re-running a seed reproduces its file except timings
and `started_utc`. Provenance in each result file: P1 rules sha256, criteria/params digests (params digest equals P0's), per-file code hashes,
git state, library versions. The preregistered text is pinned by `tests/test_intervention_p1.py::test_p1_preregistration_text_is_frozen`.
