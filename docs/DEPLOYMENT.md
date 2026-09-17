# Proteus: Production Deployment & Operations Guide

This guide details the deployment architecture, containerization workflows, versioned artifact management, controlled redeployment procedures, and observability infrastructure for **Proteus (Drift-Aware, GAN-Augmented Intrusion Detection for Software-Defined Networks)**.

---

## 1. System Architecture

Proteus cleanly separates **offline research, training, and benchmarking** from **online real-time inference and telemetry**:

```
+---------------------------------------------------------------------------------------------+
|                                    PROTEUS ARCHITECTURE                                     |
+---------------------------------------------------------------------------------------------+

      [ Ingress Network Traffic / Testbed ]
                        |
                        v (OpenFlow 1.3 Flow Stats / DPI)
      +-----------------------------------+
      |      Ryu SDN Controller (s1)      | <---- OpenFlow Telemetry Layer
      +-----------------------------------+
                        |
                        v (Feature Extraction / Mapping)
      +-----------------------------------+
      |       FastAPI Inference API       | <==== Container: proteus-api (:8000)
      |   - /predict (single & batch)     |       - Real-time scoring & validation
      |   - /health, /version, /model     |       - Versioned release management
      |   - /metrics (Prometheus / JSON)  |       - Bounded-buffer adaptive retraining
      +-----------------------------------+
                        ^
                        | (REST / JSON API)
      +-----------------------------------+
      |    Next.js Operations Console     | <==== Container: proteus-frontend (:3000)
      |   - Live telemetry & drift alerts |       - Standalone Turbopack build
      |   - Model manifest & releases     |       - Historical evaluation traces
      +-----------------------------------+
```

---

## 2. Model Artifact Management & Release Versioning

Model artifacts are managed under `models/releases/` as immutable, versioned bundles with cryptographic SHA256 checksums, with `models/active_release.json` maintaining the active production pointer:

```
models/
├── releases/
│   ├── v001/
│   │   ├── model.joblib            # Serialized RandomForestClassifier
│   │   ├── feature_schema.json     # Ordered input feature names and data types
│   │   ├── label_encoder.json      # Class index to class name mapping
│   │   └── manifest.json           # Model metadata, training parameters, SHA256 hash
│   └── v002/
│       ├── model.joblib
│       ├── feature_schema.json
│       ├── label_encoder.json
│       └── manifest.json
└── active_release.json             # Pointer to currently active release (e.g. v001)
```

### Manifest Schema (`models/releases/v001/manifest.json`)
```json
{
  "release_version": "v001",
  "version": "1.0.0",
  "created_at": "2026-09-17T18:42:29Z",
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
      "file": "model.joblib",
      "sha256": "7ebc8088ae54d10768914353263761814335502b04314efd3be7bcc3480d781a",
      "size_bytes": 1054321
    },
    "schema": {
      "file": "feature_schema.json",
      "sha256": "3a7b...9e10"
    }
  }
}
```

### Exporting & Promoting a New Model Release
```bash
# Export release v002 and promote to active
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py --version v002
```

---

## 3. Deployment Options

### Option A: Docker Compose Deployment (Recommended)
Suitable for containerized deployment on a Linux machine or server:
```bash
# 1. Build and start services in background
docker compose up --build -d

# 2. Check service status
docker compose ps

# 3. View operational logs
docker compose logs --tail=100 -f api
docker compose logs --tail=100 -f frontend
```

### Option B: Local Bare-Metal Development
```bash
# 1. Start Backend API
source .venv/bin/activate
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload

# 2. Start Next.js Frontend (in a separate terminal)
cd frontend
npm run dev -- -p 3000
```

---

## 4. API Reference & Verification

| Method | Path | Description | Output Format |
|---|---|---|---|
| `GET` | `/health` / `/api/health` | Liveness, uptime, model load state, active release | JSON |
| `GET` | `/version` / `/api/version` | API version, model release version, runtime info | JSON |
| `GET` | `/model` / `/api/model` | Active model manifest, feature schema, and label encoder | JSON |
| `GET` | `/metrics` / `/api/metrics` | Request count, latency, error count, class distribution | JSON or Prometheus (`?format=prometheus`) |
| `POST` | `/predict` / `/api/predict` | Real-time flow prediction (single vector or batch) | JSON |

### Sample Prediction Request
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "features": [0.0, 1.0, 0.0, 0.5, 120.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
  }'
```

---

## 5. Operations & Redeployment Workflows

> [!IMPORTANT]
> **Terminology Notice**: Container rebuild and restart workflows using Docker Compose are **Controlled Redeployments / Safe Rebuilds**, NOT zero-downtime blue-green deployments. A brief restart gap of 1–2 seconds occurs when restarting the container.

### A. First Deployment
```bash
# 1. Export baseline release v001
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py --version v001

# 2. Build and launch services
docker compose up --build -d

# 3. Verify health & endpoints
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8000/version | jq .
curl -s http://localhost:8000/model | jq .
curl -s http://localhost:8000/metrics?format=prometheus
```

### B. Controlled Redeployment After Code Changes
```bash
# 1. Pull latest changes
git pull origin master

# 2. Run test suites locally before deployment
PYTHONPATH=. .venv/bin/pytest tests/ -v

# 3. Rebuild and restart containers
docker compose build api frontend
docker compose up -d api frontend

# 4. Verify post-deploy health and run smoke test
curl -s http://localhost:8000/health | jq .
PYTHONPATH=. .venv/bin/python -c "
from api.server import predict, PredictionRequest
res = predict(PredictionRequest(features=[0.5]*52))
print('Smoke test status:', res.status)
"
```

### C. Model Update & Release Promotion
```bash
# 1. Train and evaluate new model (offline pipeline)
# 2. Export and register new version (e.g. v002)
PYTHONPATH=. .venv/bin/python scripts/export_deployment_artifact.py --version v002

# 3. Restart API service to reload active model
docker compose restart api

# 4. Verify updated model release loaded
curl -s http://localhost:8000/version | jq .release_version
```

### D. Model Rollback Procedure
```bash
# 1. List available model releases
PYTHONPATH=. .venv/bin/python scripts/rollback_model.py --list

# 2. Rollback active pointer to previous version
PYTHONPATH=. .venv/bin/python scripts/rollback_model.py --rollback-previous

# (Or switch to an explicit release version)
# PYTHONPATH=. .venv/bin/python scripts/rollback_model.py --version v001

# 3. Restart API service
docker compose restart api

# 4. Confirm active release
curl -s http://localhost:8000/model | jq .manifest.release_version
```

---

## 6. SDN Controller Integration & Architectural Boundaries

1. **Feature Separation**:
   - OpenFlow 1.3 `OFPFlowStatsReply` provides **10 aggregate flow statistics** (packet counters, byte counters, duration, packet rate, byte rate).
   - Datasets like CICIDS2017 require **80 deep packet inspection (DPI) features** extracted via flow meters.
   - In live SDN mode, `sdn/topology/feature_mapper.py` standardizes available OpenFlow counters into the model input vector.

2. **Privilege Requirements**:
   - Mininet virtual network emulation requires Linux `root` / `sudo` privileges to initialize Open vSwitch datapaths and network namespaces (`sdn/topology/smoke_test.sh`).
   - In unprivileged environments, Proteus operates in **Real Data Replay Mode** (`RealDataReplaySource`).

---

## 7. Security & Environment Hardening

1. **Non-Root Containers**: Both `Dockerfile.api` (user `proteus`, UID 1001) and `Dockerfile.frontend` (user `nextjs`, UID 1001) run with non-root security contexts.
2. **Secrets & Credentials**: No cloud credentials, API tokens, or dataset keys are baked into images or committed to git.
3. **Network Isolation**: API and frontend communicate over a private bridge network (`proteus-net`).
