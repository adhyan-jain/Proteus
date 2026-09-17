# Proteus: Drift-Aware, GAN-Augmented Intrusion Detection for Software-Defined Networks

**Proteus** is an adaptive, closed-loop network intrusion detection architecture designed to mitigate concept drift in Software-Defined Networks (SDN). By monitoring classifier prediction confidence shifts via a two-sample Kolmogorov-Smirnov (KS) test, Proteus triggers targeted generative augmentation using a conditional Wasserstein GAN with Gradient Penalty (WGAN-GP), filters synthetic samples through a Maximum Mean Discrepancy (MMD) fidelity gate, and performs bounded-memory adaptive retraining (`BoundedBufferClassifier`) to maintain high detection rates without memory growth or retraining latency bottlenecks.

---

## 🌟 Architecture Overview

```
                      +-----------------------------+
                      |   Live / Replayed Traffic   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Random Forest IDS Model   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Prediction Confidence     |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   KS-Test Drift Detector    |
                      +--------------+--------------+
                                     | (if drift fired)
                                     v
                      +-----------------------------+
                      |    WGAN-GP Resume Training   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Minority Synthetic Batch   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   MMD Fidelity Gate Filter  |
                      +--------------+--------------+
                                     | (if admitted)
                                     v
                      +-----------------------------+
                      | BoundedBufferClassifier     |
                      | (Adaptive Retraining)       |
                      +-----------------------------+
```

---

## 🔑 Key Features & Technical Contributions

1. **Closed-Loop Drift Adaptation**: Monitors deployed model confidence distribution shifts via a two-sample Kolmogorov-Smirnov test ($\alpha=0.05$) without requiring ground-truth drift labels.
2. **Conditional WGAN-GP Minority Augmentation**: Resumes GPU training on minority attack classes upon drift detection to generate candidate synthetic attack samples.
3. **MMD Fidelity Gate**: Applies an unbiased Gaussian-kernel Maximum Mean Discrepancy two-sample statistic ($\tau=0.25$) to reject low-quality or out-of-distribution synthetic samples before retraining.
4. **Bounded-Memory Adaptive Retraining (`BoundedBufferClassifier`)**: Replaces full historical retraining with a bounded reference reservoir ($N_{\text{ref}}=20,000$) and sliding adaptation buffer ($N_{\text{recent}}=5,000$). Guarantees $O(1)$ constant adaptation dataset buffer size ($|D_{\text{adapt}}| \le 25,000$ rows; total process RSS $\approx 5.4\text{ GB}$) and sub-3.5s update latency per drift event.
5. **Strict Non-Leakage Evaluation Protocol**: Evaluates all post-adaptation metrics on a 30% held-out evaluation split per window (`split_eval_fit`) that is never used during classifier fitting or GAN training.

---

## 📊 Summary Execution Metrics (CICIDS2017 Real Temporal Split)

Evaluated on real CICIDS2017 temporal split (Monday–Thursday training pool vs. Friday holdout replay containing unseen attack families `Bot`, `Bot-Attempted`, `DDoS`, `PortScan`):

| Condition | Baseline RF | Static Augmentation | Closed-Loop (`BoundedBufferClassifier`) |
|---|---|---|---|
| **Pre-Drift Macro-F1 (w0-w5)** | 0.4578 | 0.4578 | 0.4578 |
| **Final Window Macro-F1 (w15)** | 0.0294 | 0.0297 | **0.1738** |
| **Post-Drift Mean Macro-F1 (w6-w15)** | 0.0294 | 0.0298 | **0.1495** |
| **Active Class Macro-F1 (Final w15)** | 14.71% | 14.85% | **86.90%** |
| **Relative Macro-F1 Ratio (Final w15)** | 1.0x (ref) | 1.01x | **5.91x** (5.08x on post-drift mean) |
| **Mean Step Update Latency** | — | — | **3.47 s** |
| **Peak Memory Footprint** | — | — | **5.4 GB (flat, zero swap)** |

*Note on Macro-F1*: Friday stream windows contain ground-truth instances for only 5 active classes (`BENIGN`, `Bot`, `Bot - Attempted`, `DDoS`, `PortScan`). Standard 25-class zero-division macro-averaging (`zero_division=0`) assigns 0 F1 to the 20 inactive classes, establishing a theoretical maximum score of $5/25 = 0.2000$. Closed-loop adaptation achieves **86.90% Macro-F1 on active classes** ($\approx 87\%$ of theoretical maximum, exactly $0.8690 \times \frac{5}{25} = 0.1738$), whereas the baseline achieves 0.0% F1 on all attack classes.

---

## ⚡ Quick Start & Reproduction

### Prerequisites
```bash
git clone https://github.com/adhyan-jain/Proteus.git
cd Proteus
```

### 1. Verify GPU & Environment
```bash
.venv/bin/python -c "import torch; assert torch.cuda.is_available(); print('GPU:', torch.cuda.get_device_name(0))"
```

### 2. Run Automated Test Suite
```bash
.venv/bin/pytest tests/ -v
.venv-ryu/bin/python -m unittest discover -s sdn/topology -p "test_*.py" -v
```

### 3. Run Demo Pipeline & UI
```bash
# Run demo pipeline script
.venv/bin/python run_pipeline.py

# Launch Streamlit demo UI
.venv/bin/streamlit run app.py --server.headless true --server.port 8501
```

### 4. Production API & Containerized Deployment
```bash
# Export production model artifacts
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py

# Launch API and Next.js frontend with Docker Compose
docker compose up --build -d

# Check service health
curl -s http://localhost:8000/health | jq .
```

### 5. Run Full-Scale Evaluation & Paper Figures
```bash
# Run Stage 7 evaluation
.venv/bin/python -c "from proteus.evaluate_full import run_stage7; run_stage7(n_seeds=1)"

# Generate publication figures
.venv/bin/python paper/generate_figures.py
```

See `docs/REPRODUCIBILITY.md` for full step-by-step reproduction instructions and `docs/DEPLOYMENT.md` for production containerization details.

---

## 📄 Documentation Directory

- [`ARCHITECTURE.md`](ARCHITECTURE.md): Detailed system shape and data pipelines.
- [`STATUS.md`](STATUS.md): Current execution status, verification state, and active blockers.
- [`METRICS_HISTORY.md`](METRICS_HISTORY.md): Structured chronological record of every executed metric.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): Containerization, model artifact management, and API reference.
- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md): Step-by-step academic reproduction guide.
- [`docs/PAPER_EVIDENCE_MAP.md`](docs/PAPER_EVIDENCE_MAP.md): Claim-by-claim mapping between paper statements and source artifacts.
- [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md): Documented trade-offs, scope boundaries, and open technical limitations.
