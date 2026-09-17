# Proteus: Production Deployment & Operations Guide

This guide details the deployment architecture, containerization workflows, artifact management, and monitoring infrastructure for the **Proteus Drift-Aware, GAN-Augmented Intrusion Detection System**.

---

## 1. System Architecture

Proteus separates **offline research & retraining** from **online real-time inference & telemetry**:

```
+-----------------------------------------------------------------------------+
|                          PROTEUS ARCHITECTURE                               |
+-----------------------------------------------------------------------------+

      [ Emulated / Live Network ]
                   |
                   v (OpenFlow 1.3 Flow Stats / DPI)
      +----------------------------+
      |  Ryu SDN Controller (s1)   | <---- OpenFlow Telemetry Layer
      +----------------------------+
                   |
                   v (Feature Extraction)
      +----------------------------+
      |   FastAPI Inference API    | <==== Container: proteus-api (:8000)
      |  - /predict                |       - Real-time scoring
      |  - /health, /version       |       - Schema validation
      |  - /metrics (Prometheus)   |       - Bounded-buffer adaptation
      +----------------------------+
                   ^
                   | (REST / JSON API)
      +----------------------------+
      | Next.js Operations Console | <==== Container: proteus-frontend (:3000)
      | - Drift & Fidelity Stream  |       - Multi-screen dashboard
      | - Model & Experiment View  |       - Topology & telemetry charts
      +----------------------------+
```

---

## 2. Model Artifact Management & Schema

Model artifacts are managed under `models/` with cryptographically verified checksums and strict schema validation:

```
models/
├── baseline_rf.joblib      # Serialized scikit-learn RandomForestClassifier
├── feature_schema.json     # Ordered list of expected input features and data types
├── label_encoder.json      # Mapping between class indices and human-readable names
└── manifest.json           # Model metadata, training parameters, SHA256 checksums
```

### Manifest Structure (`models/manifest.json`)
```json
{
  "version": "1.0.0",
  "created_at": "2026-09-17T17:50:11Z",
  "model_type": "RandomForestClassifier",
  "parameters": {
    "n_estimators": 100,
    "max_depth": 15,
    "random_state": 42
  },
  "training_metadata": {
    "dataset": "NSL-KDD-Schema-Reference",
    "n_samples": 5000,
    "n_features": 52,
    "n_classes": 5
  },
  "artifacts": {
    "model": {
      "file": "baseline_rf.joblib",
      "sha256": "7ebc8088ae54d10768914353263761814335502b04314efd3be7bcc3480d781a"
    }
  }
}
```

### Exporting New Model Artifacts
To train or export a model artifact into production format:
```bash
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py
```

---

## 3. Containerized Deployment (Docker Compose)

### Prerequisites
- Docker Engine $\ge 24.0$
- Docker Compose $\ge 2.20$

### Quick Start
```bash
# Build and launch both API and Frontend in background
docker compose up --build -d

# Check service status
docker compose ps

# View real-time logs
docker compose logs -f
```

The services will be available at:
- **Web Dashboard**: `http://localhost:3000`
- **Inference & Health API**: `http://localhost:8000`
- **Interactive OpenAPI Docs**: `http://localhost:8000/docs`
- **Prometheus Metrics**: `http://localhost:8000/metrics?format=prometheus`

---

## 4. Local Bare-Metal Setup

### 1. Backend Service (FastAPI)
```bash
# Activate virtual environment
source .venv/bin/activate

# Ensure model artifacts exist
python scripts/export_deployment_artifact.py

# Start API server
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Dashboard (Next.js)
```bash
cd frontend
npm install
npm run build
npm start -- -p 3000
```

---

## 5. API Reference & Endpoints

| Method | Path | Description | Output Format |
|---|---|---|---|
| `GET` | `/health` / `/api/health` | Service liveness & component status | JSON |
| `GET` | `/version` / `/api/version` | API and model version metadata | JSON |
| `GET` | `/model` / `/api/model` | Loaded model manifest & schema | JSON |
| `GET` | `/metrics` / `/api/metrics` | Request, error, latency & class metrics | JSON or Prometheus (`?format=prometheus`) |
| `POST` | `/predict` / `/api/predict` | Real-time flow classification | JSON (`SinglePredictionResult` / Batch) |
| `GET` | `/api/experiments/*` | Historical research evaluation traces | JSON |

### Sample Prediction Request
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "features": [0.0, 1.0, 0.0, 0.5, 120.0, ... 52 features total ...]
  }'
```

Response:
```json
{
  "status": "success",
  "count": 1,
  "predictions": [
    {
      "predicted_label": "benign",
      "predicted_index": 0,
      "probabilities": {
        "benign": 0.98,
        "dos": 0.01,
        "probe": 0.005,
        "r2l": 0.003,
        "u2r": 0.002
      },
      "inference_time_ms": 1.42
    }
  ],
  "total_time_ms": 1.55
}
```

---

## 6. Redeployment & Rollback Procedures

### Rolling Redeployment
When updating model artifacts or application code:
```bash
# 1. Export or verify new model artifacts
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py

# 2. Rebuild and restart containers without downtime
docker compose up --build -d --no-deps api
docker compose up --build -d --no-deps frontend
```

### Rollback Procedure
1. Revert `models/baseline_rf.joblib` and `models/manifest.json` from backup or git history:
   ```bash
   git checkout HEAD~1 -- models/
   ```
2. Restart the API container:
   ```bash
   docker compose restart api
   ```
3. Verify health and loaded model version:
   ```bash
   curl -s http://localhost:8000/health | jq .
   curl -s http://localhost:8000/version | jq .
   ```

---

## 7. SDN Deployment Boundary & Known Limitations

1. **Feature Separation**:
   - OpenFlow 1.3 `OFPFlowStatsReply` provides 10 aggregated packet/byte counters and duration stats.
   - CICIDS2017 / InSDN 80-feature datasets require Deep Packet Inspection (DPI) flow meters (e.g. CICFlowMeter).
   - In live SDN mode, `sdn/topology/feature_mapper.py` standardizes available OpenFlow telemetry into the model input vector.

2. **Privilege Requirements**:
   - Mininet virtual network emulation requires Linux `root` / `sudo` privileges to configure network namespaces and Open vSwitch kernels.
   - In non-root or containerized environments without `--privileged` flags, Proteus operates in **Real Data Replay Mode** (`RealDataReplaySource`).
