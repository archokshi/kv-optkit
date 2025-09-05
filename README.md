# KV-OptKit

KV-OptKit is a drop-in optimization layer for LLM inference that observes runtime behavior and continuously recommends—or automatically enforces—settings to keep KV-cache memory, batching, and tiered storage within budget while meeting P95 latency SLOs.

## Features

- **Advisor Mode**: Read-only recommendations for KV-cache optimization
- **SIM Adapter**: No-GPU testing environment included
- **Policy Engine**: Configurable policies for eviction and memory management
- **REST API**: Easy integration with existing systems
- **Docker Support**: Containerized deployment
- **Autopilot Mode**: Automated optimization with safety guards and shadow testing

## Quick Start

### Prerequisites

- Python 3.10+
- Docker and Docker Compose (for containerized deployment)

### Local Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd kv-optkit
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the server (SIM adapter by default):
   ```bash
   # Option A: use the sample config
   set KVOPT_CONFIG=config\sample_config.yaml   # Windows PowerShell: $env:KVOPT_CONFIG="config/sample_config.yaml"
   kvopt-server  # serves on :9000
   # or
   python -m kvopt.server.main
   ```

5. Verify health:
   ```bash
   curl http://localhost:9000/healthz
   ```

6. In another terminal, run the demo (generates activity for SIM):
   ```bash
   python examples/demo_trace.py
   ```

### Docker Compose

1. Build and start the service:
   ```bash
   docker compose -f docker/compose.yml up --build -d
   ```

2. Check the service status:
   ```bash
   docker compose -f docker/compose.yml ps
   ```

3. Run the demo:
   ```bash
   python examples/demo_trace.py
   ```

## API Documentation

### Health Check

```
GET /healthz
```

### Get Advisor Report

```
GET /advisor/report
```

### SIM Adapter Endpoints (for testing)
The SIM adapter is used internally for local testing. Interact with the public endpoints below:

- `GET /telemetry` — current adapter telemetry
- `GET /metrics` — Prometheus metrics

## Autopilot Mode

The Autopilot feature automates KV cache optimization with safety guarantees:

### Key Components

1. **Policy Engine**: Generates optimization plans based on system state
2. **Guard System**: Validates and monitors plan execution with rollback capability
3. **Action Executor**: Safely applies optimization actions
4. **REST API**: Control and monitor the optimization process

### Using Autopilot

#### 1. Create an Optimization Plan

```bash
curl -X POST "http://localhost:9000/autopilot/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "target_hbm_util": 0.7,
    "max_actions": 5,
    "priority": "high"
  }'
```

#### 2. Check Plan Status

```bash
curl "http://localhost:9000/autopilot/plan/{plan_id}"
```

#### 3. Monitor Metrics

```bash
curl "http://localhost:9000/autopilot/metrics"
```

### Python example (requests)

```python
import requests

base = "http://localhost:9000"

# Create a plan
r = requests.post(
    f"{base}/autopilot/plan",
    json={"target_hbm_util": 0.7, "max_actions": 5, "priority": "high"},
)
r.raise_for_status()
plan_id = r.json()["plan_id"]

# Poll status
s = requests.get(f"{base}/autopilot/plan/{plan_id}").json()
print("status:", s["status"], "completed:", s["actions_completed"], "/", s["actions_total"]) 

# Metrics
m = requests.get(f"{base}/autopilot/metrics").json()
print("guard metrics:", m)
```

## Configuration

Edit `config/sample_config.yaml` to customize the behavior:
```yaml
slo:
  latency_p95_ms: 2000.0
  max_accuracy_delta_pct: 0.5

budgets:
  hbm_util_target: 0.85
  offload_bw_gbps: 120.0

policy:
  keep_recent_tokens: 4096
  eviction:
    - age_decay
  tiers:
    - HBM
    - DDR
    - CXL
    - NVMe

plugins: {}

guardrails:
  ab_shadow_fraction: 0.05
  rollback_on_acc_delta: true

autopilot:
  enabled: true
  default_target_hbm_util: 0.8
  default_max_actions: 10
  default_priority: "medium"

guard:
  enabled: true
  shadow_fraction: 0.1  # Fraction of requests to execute in shadow mode
  max_accuracy_delta: 0.05  # Maximum allowed accuracy impact
  rollback_on_high_impact: true
  accuracy_weights:
    evict: 1.0
    offload: 0.8
    quantize: 0.5

policy_engine:
  min_sequence_length: 100
  min_sequence_utilization: 0.3
  quantization_scales: [0.5, 0.25]
  action_priority: ["EVICT", "OFFLOAD", "QUANTIZE"]
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

This project uses `black` for code formatting and `flake8` for linting.

```bash
black .
flake8
```

## Installation and Quickstart

- pip (PyPI):

```bash
pip install kv-optkit

# Optional: point to a custom config (PowerShell)
$env:KVOPT_CONFIG = "config/sample_config.yaml"

# Start the server on :9000
kvopt-server
```

- pip with extras:

```bash
# vLLM adapter support and NVML telemetry
pip install "kv-optkit[vllm]"

# TensorRT-LLM route (Linux-only for TensorRT)
pip install "kv-optkit[trtllm]"

# Text Generation Inference route
pip install "kv-optkit[tgi]"

# DeepSpeed-MII route
pip install "kv-optkit[deepspeed]"

# Dev tools for contributing (pytest, ruff, mypy, etc.)
pip install -e ".[dev]"
```

Extras summary:

- `vllm`: vLLM engine adapter and NVML GPU telemetry.
- `trtllm`: TensorRT-LLM and Triton client tooling (Linux preferred).
- `tgi`: Text Generation Inference client/adapter.
- `deepspeed`: DeepSpeed-MII adapter route.
- `dev`: local development and CI tooling.

- Docker (GHCR):

```bash
docker run -p 9000:9000 ghcr.io/archokshi/kv-optkit:latest
```

- Docker Compose profiles:

```bash
# Agent only
docker compose -f docker/compose.yml --profile sim up -d

# Observability (Prometheus + Grafana)
docker compose -f docker/compose.yml --profile obs up -d
```

- Helm (local chart):

```bash
helm upgrade --install kv-optkit ./deploy/helm/kv-optkit \
  --set image.repository=ghcr.io/archokshi/kv-optkit \
  --set image.tag=latest
```

### Environment configuration (Sidecar/Auto-attach)

- `KVOPT_ENGINE_ENDPOINT`: target engine endpoint (e.g., `http://localhost:8000`).
- `KVOPT_ENGINE_SETTINGS`: optional JSON settings blob consumed at server startup.

These variables are read at server start; sidecar mode uses them to auto-attach.

## Observability & Reporting

Provides Prometheus metrics, a Grafana dashboard, and a report generator for go/no-go decisions.

### Metrics exposed at `/metrics`

- Gauges
  - `kvopt_hbm_utilization`
  - `kvopt_hbm_used_gb`
  - `kvopt_p95_latency_ms`
  - `kvopt_ttft_ms`
  - `kvopt_ddr_utilization`
  - `kvopt_ddr_used_gb`
- Counters
  - `kvopt_tokens_evicted_total`
  - `kvopt_tokens_quantized_total`
  - `kvopt_reuse_hits_total`, `kvopt_reuse_misses_total`
  - `kvopt_autopilot_applies_total`, `kvopt_autopilot_rollbacks_total`

Prometheus exposition is compliant (`text/plain; version=0.0.4`) with HELP/TYPE headers.

### Docker Compose stack

From `docker/` directory:

```bash
docker compose -f docker/compose.yml up -d prometheus grafana
```

- Prometheus UI: http://localhost:9090
  - Example queries: `kvopt_hbm_utilization`, `kvopt_p95_latency_ms`, `kvopt_ttft_ms`
- Grafana UI: http://localhost:3000
  - Dashboard: "KV-OptKit" (provisioned via `docker/grafana-dashboard.json`)

### Report generator

Generate a live report by sampling metrics for ~30s:

```bash
python tools/make_report.py --from live --base http://localhost:8000 --samples 6 --interval 5 --out outputs/run_report.md
```

Or from a CSV (CI-friendly):

```bash
python tools/make_report.py --from file --csv tests/fixtures/metrics_sample.csv --out outputs/run_report.md
```

Artifacts:

- Markdown: `outputs/run_report.md`
- Charts in `outputs/charts/`: `hbm.png`, `latency.png`, `ttft.png`, `ddr.png`

The report includes before/after summaries, action counter deltas, and a Go/No-Go decision vs the P95 SLO.

## QuickView Screenshots

Below are example views from the built-in QuickView at `/`.

- Overview dashboard with HBM utilization, adapter capabilities, and sequence counts
  ![QuickView Overview](docs/quickview_overview.png)

- Sequences table with per-sequence utilization and qscale
  ![QuickView Sequences](docs/quickview_sequences.png)

- Autopilot controls and current plan status
  ![QuickView Autopilot](docs/quickview_autopilot.png)

Place your screenshots in `docs/` with the file names above or adjust links as needed.

## Containerized LMCache demo

The demo runs entirely in Docker and writes results to a host-mounted folder.

### Build the demo image

```bash
docker build -f Dockerfile.demo -t kvopt-demo .
```

### Start with Docker Compose

```bash
docker compose -f docker/compose.yml up --force-recreate
```

This launches:
- `redis:7` as `kvopt-redis`
- `kvopt-demo` running `examples/demo_reuse.py` against `redis://redis:6379`

### Where results are saved

- CSV output is persisted on the host at `outputs/kv_reuse.csv`.
- On Windows, you can inspect it with:
  ```powershell
  type outputs\kv_reuse.csv
  ```

### Stopping containers

In the same directory:
```bash
docker compose -f docker/compose.yml down
```

## Compatibility matrix

The following combinations have been smoke-tested with the SIM adapter (no GPU) and with vLLM where noted.

| Component | Version(s) |
|---|---|
| Python | 3.10, 3.11 |
| vLLM (optional) | 0.5.x (basic adapter compatibility) |
| CUDA | N/A for SIM; 12.x recommended for GPU deployments |
| GPU SKUs (indicative) | A10, A100 40/80GB, L4 (adapter-level tests) |

Notes:
- SIM adapter requires no GPU and is the default for quickstart.
- For GPU deployments with vLLM, ensure CUDA drivers match container/base image.

## Adapters & capability levels

| Adapter | Levels | Notes |
|---|---|---|
| vLLM | L0, L2 | L0 observe-only; L2 safe EVICT-only apply |
| SIM | L0–L3 | Full feature surface for development/testing |
| TGI | L0 | Early support; subject to change |
| DeepSpeed-MII | L0 | Early support; subject to change |

## Releases

- Semantic Versioning (`vX.Y.Z`).
- Release notes and change history: see [CHANGELOG.md](CHANGELOG.md).
- Pin a specific version:
  - PyPI: `pip install kv-optkit==X.Y.Z`
  - GHCR: `ghcr.io/archokshi/kv-optkit:X.Y.Z`

## License

Apache 2.0 - See [LICENSE](LICENSE) for more information.
