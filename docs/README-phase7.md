# KV-OptKit Phase 7 – GPU Scaffolding

This guide shows two ways to validate Phase 7:
- No‑GPU development path (SIM) to validate KV‑OptKit + Prometheus + Grafana on Windows
- Real GPU path (vLLM CUDA) to validate end‑to‑end inference, TTFT/P95, and LMCache panels

Prerequisites
- Docker and Docker Compose
- For GPU path: NVIDIA GPU + driver, Docker + NVIDIA Container Toolkit, or Docker Desktop with WSL2 GPU

Dashboards
- Grafana: <http://localhost:3000> → folder `KV-OptKit` → dashboard `KV‑OptKit Phase 7 – GPU`
- Prometheus: <http://localhost:9090/targets>

---

## A) No‑GPU development path (SIM)

Use this on Windows without a GPU to verify wiring and basic metrics.

```powershell
$env:KVOPT_ADAPTER = "sim"
$env:UPSTREAM_VLLM_URL = ""

docker compose -f docker/demos/gpu/docker-compose.gpu.baseline.yaml `
  up -d --build --no-deps kvopt prometheus grafana

# Generate some traffic
1..150 | % {
  Invoke-RestMethod http://localhost:9001/healthz    | Out-Null
  Invoke-RestMethod http://localhost:9001/v1/hw      | Out-Null
  Invoke-RestMethod http://localhost:9001/v1/workload| Out-Null
  Invoke-RestMethod http://localhost:9001/v1/profile | Out-Null
  Start-Sleep -Milliseconds 120
}
```

Verify
- Prometheus targets: `kvopt` is UP; `vllm` is DOWN (expected)
- Grafana loads Phase 7 dashboard (GPU/TTFT/LMCache panels show “No data”, expected)

---

## B) GPU validation path (vLLM CUDA)

Run this on a GPU host (WSL2 GPU on Windows, native Linux, or a cloud GPU VM).

```powershell
# Build CUDA vLLM image (one-time)
docker build -f docker/Dockerfile.vllm_gpu_cuda -t kvopt/vllm-gpu:dev .

# Bring up baseline GPU stack (vLLM + KV‑OptKit + Prometheus + Grafana)
docker compose -f docker/demos/gpu/docker-compose.gpu.baseline.yaml up -d --build

# Warm + short traffic
powershell -ExecutionPolicy Bypass -File scripts/demos/run_gpu_scenario.ps1 `
  -Compose docker/demos/gpu/docker-compose.gpu.baseline.yaml `
  -Scenario baseline_gpu -StayUp
```

Advisor + LMCache stack
```powershell
docker compose -f docker/demos/gpu/docker-compose.gpu.advisor.lmcache.yaml up -d --build
powershell -ExecutionPolicy Bypass -File scripts/demos/run_gpu_scenario.ps1 `
  -Compose docker/demos/gpu/docker-compose.gpu.advisor.lmcache.yaml `
  -Scenario advisor_with_lmcache_gpu -StayUp
```

Expected
- Prometheus: both `kvopt` and `vllm` targets UP
- Grafana: GPU Utilization, HBM Used/Util, TTFT and P95 populate during traffic
- LMCache hits/misses/bytes populate in the advisor+LMCache stack

---

## PromQL snippets

Paste in Prometheus Graph:
- `up{job="kvopt"}`
- `up{job="vllm"}`
- `sum(rate(kvopt_request_latency_seconds_count[1m]))`
- `histogram_quantile(0.95, sum(rate(kvopt_request_latency_seconds_bucket[5m])) by (le))`
- `kvopt_ttft_ms`
- `kvopt_hbm_used_gb`
- `kvopt_hbm_utilization`
- `rate(kvopt_apply_success_total[5m])`
- `rate(kvopt_lmcache_hits_total[5m])`
- `rate(kvopt_lmcache_misses_total[5m])`

---

## Troubleshooting

- Grafana port 3000 already in use
  - Stop the conflicting container (e.g., `open-webui`) or change the mapping in compose.
- vLLM target DOWN on GPU host
  - Ensure the baseline GPU stack is up and the CUDA image built. Check container logs.
- WSL2 GPU not visible to Docker Desktop
  - Update NVIDIA driver, enable WSL integration, run `wsl --update` and restart Docker Desktop.

---

## Notes

- The no‑GPU path is intended for wiring validation; GPU/LMCache panels will show “No data”.
- The GPU path requires real hardware; Colab can be used for token generation smoke tests but not for the full Docker/Compose observability stack.
