# KV-OptKit Demo Guide

This guide walks you through the demos included with KV-OptKit. It is designed for a quick, delightful developer experience.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Horizontal Phases](#horizontal-phases)
- [Phase 1: Advisor (Recommendations Only)](#phase-1-advisor-recommendations-only)
- [Phase 2: Autopilot (Combined Plan)](#phase-2-autopilot-combined-plan)
- [Phase 2: Individual Action Demos](#phase-2-individual-action-demos)
- [Phase 3: Policy/Governor](#phase-3-policygovernor)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Next Steps](#next-steps)
- [Phase 4: Observability & Reporting](#phase-4-observability--reporting)
- [Phase 5: Sidecar and vLLM Demos](#phase-5-sidecar-and-vllm-demos)
  - [Phase 5 Quick Checklist](#phase-5-quick-checklist)
  - [Phase 5.A: CPU-only — SIM (L3 End-to-End)](#phase-5a-cpu-only--sim-l3-end-to-end)
  - [Phase 5.B: CPU-only — vLLM Adapter with Demo Sequences (L2)](#phase-5b-cpu-only--vllm-adapter-with-demo-sequences-l2)
  - [Phase 5.C: CPU-only — vLLM Adapter + Sidecar Sequence Injection](#phase-5c-cpu-only--vllm-adapter--sidecar-sequence-injection)
  - [Phase 5.D: GPU-backed — vLLM + Sidecar Proxy](#phase-5d-gpu-backed--vllm--sidecar-proxy-openai-compatible-streaming-supported)
  - [Dev Hooks (PowerShell quick commands)](#dev-hooks-powershell-quick-commands)
- [Troubleshooting (Phase 5)](#troubleshooting-phase-5)
- [Phase 5: Validation](#phase-5-validation)
  - [Telemetry Parity (NVIDIA/AMD/torch)](#telemetry-parity-nvidiaamdtorch)
  - [Governor Verification](#governor-verification)
  - [Apply Toggle](#apply-toggle)
- [Phase 6: CPU A/B Demos](#phase-6-cpu-ab-demos)
- [Phase 7: GPU Scaffolding](#phase-7-gpu-scaffolding)
- [Maintainers: In-Process vLLM Hook Wiring](#maintainers-in-process-vllm-hook-wiring)

## Prerequisites

- Windows PowerShell (examples use `.ps1` scripts)
- Python 3.10+
- A virtual environment with project dependencies installed

Start the server in a separate terminal for all demos:

```powershell
$env:KVOPT_PORT=9001
python -m kvopt.server.main
```

---

## Horizontal Phases

Horizontal phases apply to every demo phase. Start here first:

- HP1: Discovery – hardware/runtime detection, workload hints, profile selection, and safe provisioning plan.
  - See: [README-HP1-Discovery.md](README-HP1-Discovery.md)

---

## Phase 1: Advisor (Recommendations Only)

- Script: `examples/demo_phase1_advisor.ps1`
- Purpose: Generate an advisor report with quantified recommendations; no actions are executed.

Run:
```powershell
./examples/demo_phase1_advisor.ps1
```

What you will see:
- Initial telemetry (HBM utilization, used GB, p95 latency)
- Advisor report JSON with recommendations (e.g., QUANTIZE, OFFLOAD, EVICT)
- A plain-text table summary (Step 6)
- Final telemetry showing no changes (advisory-only)

---

## Phase 2: Autopilot (Combined Plan)

- Script: `examples/demo_phase2_autopilot.ps1`
- Purpose: Create and execute a multi-step optimization plan automatically.

Run:
```powershell
./examples/demo_phase2_autopilot.ps1
```

What you will see:
- Initial telemetry
- Autopilot plan with multiple actions (QUANTIZE, OFFLOAD, EVICT)
- Final telemetry showing reduced HBM utilization

---

## Phase 2: Individual Action Demos

These isolate a single action for educational clarity.

### QUANTIZE Only
- Script: `examples/demo_phase2_quantize.ps1`
- Run:
```powershell
./examples/demo_phase2_quantize.ps1
```
- Shows reduced memory via quantization on one sequence.

### OFFLOAD Only
- Script: `examples/demo_phase2_offload.ps1`
- Run:
```powershell
./examples/demo_phase2_offload.ps1
```
- Frees HBM by offloading to DDR; may trade for a bit of latency.

### EVICT Only
- Script: `examples/demo_phase2_evict.ps1`
- Run:

```powershell
./examples/demo_phase2_evict.ps1
```
- Evicts a small token prefix to free capacity quickly.

---

## Phase 3: Policy/Governor

- Script: `examples/demo_phase3_governor.ps1`
- Purpose: Validate OFFLOAD bandwidth governor caps per tick and counters.

Run:

```powershell
./examples/demo_phase3_governor.ps1
```

What it does:
- Enables apply and seeds large sequences if needed.
- Drives OFFLOAD-only autopilot plans to create bandwidth pressure.
- Asserts governor throttling occurs and prints counters.

What you will see:
- QuickView header shows: `Governor: throttle_events N, governed_bytes M`.
- Prometheus `/metrics` includes:
  - `kvopt_governor_throttle_events_total`
  - `kvopt_offload_governed_bytes_total`
  - `kvopt_offload_tick_cap_bytes`
- Grafana panel “Governed Bytes Rate (bytes/s)” shows spikes during the demo.

Notes:
- To force clear throttling, you can reduce cap at startup:

  ```powershell
  $env:KVOPT_OFFLOAD_TICK_CAP_BYTES="1048576"  # 1 MB/tick
  $env:KVOPT_OFFLOAD_TICK_MS="500"             # 0.5 s/tick
  ```

---

## Troubleshooting

- If a demo asks you to start the server, open a new terminal and run the server command at the top of this guide.
- If the autopilot plan has no actions, ensure you submitted enough sequences; the demo scripts do this for you.
- If PowerShell blocks script execution, use:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
  ```

---

## FAQ

- Are actions exclusive? 
  - They can overlap, but the demos typically apply one action per sequence for clarity.
- Can I request only certain actions from the autopilot? 
  - Yes. The `/autopilot/plan` endpoint supports `allowed_actions` (e.g., `["QUANTIZE"]`).

---

## Next Steps

- Explore the CLI: `examples/demo_cli.py`
- Browse API: `/telemetry`, `/advisor/report`, `/autopilot/*`
- Adjust thresholds and policies via `config/` as needed.

---

---

## Phase 4: Observability & Reporting

Spin up Prometheus and Grafana, run the server, and watch metrics update from demos or Dev Hooks.

Run:

```powershell
# Start Prometheus + Grafana (Grafana on http://localhost:3001/)
docker compose -f docker/compose.yml --profile obs up -d

# In a separate terminal, run KV-OptKit (choose one)
# vLLM demo sequences (CPU-only)
$env:KVOPT_ADAPTER = "vllm"
$env:KVOPT_DEMO_SEQS = "1"
$env:KVOPT_PORT = "9001"
python -m kvopt.server.main

# or SIM adapter (CPU-only)
$env:KVOPT_ADAPTER = "sim"
$env:KVOPT_PORT = "9001"
python -m kvopt.server.main

# Optional: enable Dev Hooks before starting server to simulate Engine Activity
# $env:KVOPT_DEV = "1"

# Validate endpoints and see next steps
powershell -ExecutionPolicy Bypass -File .\examples\demo_phase4_obs.ps1
```

Open:

- QuickView: [http://localhost:9001/](http://localhost:9001/)
- Prometheus: [http://localhost:9090/](http://localhost:9090/)
- Grafana: [http://localhost:3001/](http://localhost:3001/)

Notes:

- Grafana port can be changed in `docker/compose.yml` (e.g., `3001:3000`).
- The Phase 4 demo script probes `/metrics` and `/metrics/snapshot` and prints next steps.

---

## Phase 5: Sidecar and vLLM Demos

These demos validate Phase 5 features with the same simple, copy/paste workflow as Phase 1/2.

All demos assume the server is running in a separate terminal (see top of this guide). If a demo requires a special adapter/env, it will say so explicitly.

### Phase 5 Quick Checklist

- 5.A SIM (L3)
  - Start:
    - `$env:KVOPT_ADAPTER = "sim"`
    - `$env:KVOPT_PORT = 9001`
    - `python -m kvopt.server.main`
  - Verify: QuickView loads at [http://localhost:9001/](http://localhost:9001/)
  - Run: `powershell -ExecutionPolicy Bypass -File .\examples\demo_phase5a_sim.ps1`
  - Expect: "Last Apply" shows ok; telemetry (HBM/util, sequences) updates

- 5.B vLLM (demo sequences, CPU-only)
  - Start:
    - `$env:KVOPT_ADAPTER = "vllm"`
    - `$env:KVOPT_DEMO_SEQS = 1`
    - `$env:KVOPT_PORT = 9001`
    - `python -m kvopt.server.main`
  - Verify: QuickView shows adapter=vllm; sequences > 0; capabilities include {EVICT, OFFLOAD}
  - Run: `powershell -ExecutionPolicy Bypass -File .\examples\demo_phase5b_vllm_demo.ps1`
  - Expect: Advisor recs > 0; Apply ok; `/apply/last` non-empty

- 5.C vLLM + Sidecar (CPU wiring)
  - Start server:
    - `$env:KVOPT_ADAPTER = "vllm"`
    - `$env:KVOPT_DEMO_SEQS = 0`
    - `$env:KVOPT_PORT = 9001`
    - `python -m kvopt.server.main`
  - Start sidecar:
    - `$env:UPSTREAM_VLLM_URL = "http://localhost:8000"`
    - `$env:KVOPT_URL = "http://localhost:9001"`
    - `$env:PROXY_PORT = 9010`
    - `python scripts/kvopt_sidecar_proxy.py`
  - Send request (non-streaming):
    - `curl.exe -i http://localhost:9010/v1/completions -H "Content-Type: application/json" --data-binary "{\"model\":\"dummy\",\"prompt\":\"Hello\",\"max_tokens\":16}"`
  - Expect: 502/500 if no upstream; QuickView may briefly show sequence events

### Phase 5.A: CPU-only — SIM (L3 End-to-End)

- Purpose: Full Autopilot flow on CPU (EVICT, OFFLOAD, QUANTIZE, REUSE), ideal for local validation.
- Run:
  ```powershell
  $env:KVOPT_ADAPTER = "sim"
  $env:KVOPT_PORT = 9001
  python -m kvopt.server.main
  ```
- Open QuickView: http://localhost:9001/
- Actions:
  - Click "Apply from Advisor".
  - Use the "Enable Apply" checkbox to toggle execution (server respects `/server/allow_apply`).

### Phase 5.B: CPU-only — vLLM Adapter with Demo Sequences (L2)

- Purpose: Validate vLLM wiring and UI flow without a GPU by generating realistic demo sequences.
- Run:
  ```powershell
  $env:KVOPT_ADAPTER = "vllm"
  $env:KVOPT_DEMO_SEQS = "1"
  $env:KVOPT_PORT = 9001
  python -m kvopt.server.main
  ```
- Open QuickView: http://localhost:9001/
- What to expect: L2 capabilities; Sequences KPI populated; Advisor recommendations present.
- You can toggle apply via the UI checkbox.

### Phase 5.C: CPU-only — vLLM Adapter + Sidecar Sequence Injection

- Purpose: Validate sidecar integration without a vLLM server or GPU by driving sequence lifecycle endpoints.
- Run server:
  ```powershell
  $env:KVOPT_ADAPTER = "vllm"
  $env:KVOPT_DEMO_SEQS = "0"
  $env:KVOPT_PORT = 9001
  python -m kvopt.server.main
  ```
- Inject sequences and run plan:
  ```powershell
  python scripts/sidecar_validate.py --server http://localhost:9001
  ```
- Open QuickView: http://localhost:9001/ (Sequences KPI > 0; Advisor recs available; apply toggle works).

#### Windows curl examples (PowerShell quoting-safe)

- Non-streaming request through sidecar:
  ```powershell
  curl.exe -i http://localhost:9010/v1/completions `
    -H "Content-Type: application/json" `
    --data-binary "{\"model\":\"dummy\",\"prompt\":\"Hello\",\"max_tokens\":16}"
  ```

- Streaming request through sidecar (SSE):
  ```powershell
  curl.exe -N http://localhost:9010/v1/completions `
    -H "Content-Type: application/json" `
    --data-binary "{\"model\":\"dummy\",\"prompt\":\"Stream test\",\"max_tokens\":32,\"stream\":true}"
  ```

#### Dev Hooks (PowerShell quick commands)

Use these to simulate engine events (alloc/move/free) when `KVOPT_DEV=1` before starting the server. Useful for CPU-only validation of the Engine Activity box in QuickView.

```powershell
# Enable dev hooks and start server
$env:KVOPT_DEV = "1"
$env:KVOPT_ADAPTER = "vllm"
$env:KVOPT_PORT = "9001"
python -m kvopt.server.main

# In another terminal (same venv):
# Allocation
Invoke-RestMethod -Uri http://localhost:9001/dev/hooks/alloc -Method Post `
  -Body (@{sequence_id="seqX"; bytes=4096} | ConvertTo-Json) -ContentType "application/json"

# Move (HBM -> DDR)
Invoke-RestMethod -Uri http://localhost:9001/dev/hooks/move -Method Post `
  -Body (@{sequence_id="seqX"; bytes=2048; src="HBM"; dst="DDR"} | ConvertTo-Json) -ContentType "application/json"

# Free
Invoke-RestMethod -Uri http://localhost:9001/dev/hooks/free -Method Post `
  -Body (@{sequence_id="seqX"; bytes=4096} | ConvertTo-Json) -ContentType "application/json"
```

### Phase 5.D: GPU-backed — vLLM + Sidecar Proxy (OpenAI-Compatible, Streaming Supported)

- Purpose: Show real sequences and telemetry on hardware, including streaming token updates via the proxy.
- Start vLLM (OpenAI server on port 8000):
  ```powershell
  python -m vllm.entrypoints.openai.api_server --model <MODEL_ID> --port 8000 --dtype bfloat16
  ```
- Start KV-OptKit:
  ```powershell
  $env:KVOPT_ADAPTER = "vllm"
  $env:KVOPT_DEMO_SEQS = "0"
  $env:KVOPT_PORT = 9001
  python -m kvopt.server.main
  ```
- Start sidecar proxy (port 9010):
  ```powershell
  $env:UPSTREAM_VLLM_URL = "http://localhost:8000"
  $env:KVOPT_URL = "http://localhost:9001"
  $env:PROXY_PORT = "9010"
  python scripts/kvopt_sidecar_proxy.py
  ```
- Send requests to the proxy:
  - Non-streaming:
    ```powershell
    curl -s http://localhost:9010/v1/completions -H "Content-Type: application/json" -d '{"model":"<MODEL_ID>","prompt":"Hello","max_tokens":32}'
    ```
  - Streaming (SSE):
    ```powershell
    curl -N http://localhost:9010/v1/completions -H "Content-Type: application/json" -d '{"model":"<MODEL_ID>","prompt":"Stream test","max_tokens":64,"stream":true}'
    ```
- Open QuickView: http://localhost:9001/ (sequences update; Advisor recs; apply toggle controls execution).

---

## Troubleshooting (Phase 5)

- Internal Server Error (500) or 502 from sidecar
  - Cause: Upstream vLLM is not running at `UPSTREAM_VLLM_URL` (default `http://localhost:8000`).
  - Fix: Start upstream vLLM (GPU) or accept 502 for CPU-only wiring validation; sidecar will still emit `/sequences/*` events to KV-OptKit.

- PowerShell JSON quoting errors (e.g., "unmatched close brace")
  - Cause: Using PowerShell curl alias (`Invoke-WebRequest`) or unescaped quotes.
  - Fix: Use `curl.exe` and `--data-binary` with escaped JSON as shown above.

- `kvopt-sidecar` not found
  - Cause: Console scripts not installed in your venv.
  - Fix: Run `pip install -e .` to install the package, then use `kvopt-sidecar ...`. Or run directly: `python scripts/kvopt_sidecar_proxy.py`.

- QuickView “Apply from Advisor” disabled
  - Cause: Server-wide apply toggle is off or adapter has limited capabilities.
  - Fix: Toggle apply on via QuickView checkbox or `POST /server/allow_apply {"allow": true}`. For vLLM CPU-only, only `EVICT` and `OFFLOAD` are enabled (L2).

- Port mismatches (demo scripts vs server)
  - Symptom: Demos point to 9000 but server is on 9001.
  - Fix: Set `$env:KVOPT_PORT = "9001"` before running demos. All bundled demos honor `KVOPT_PORT`.

- Advisor returns no recommendations (rare on CPU-only vLLM)
  - Cause: No sequences available; ensure demo sequences are enabled (`KVOPT_DEMO_SEQS=1`) or sidecar is sending `/sequences/*` events.
  - Fix: Use Phase 5.B or send proxy requests via sidecar to populate sequences.

---

## Phase 5: Validation

### Telemetry Parity (NVIDIA/AMD/torch)

- Purpose: Ensure reported HBM usage matches vendor sources within tolerance.
- Run:
  ```powershell
  python scripts/telemetry_parity.py --server http://localhost:9001 --device 0 --tolerance 0.05
  ```
- Expected:
  - On real hardware: deltas <= 5%.
  - On CPU-only: a warning that no vendor source is available (expected) and exit 0.

CI note:

- See GitHub Actions workflow: `.github/workflows/gpu-parity.yml`.
- Behavior:
  - Detects GPU via `nvidia-smi`.
  - If GPU present, runs the parity check and fails if >5%.
  - If no GPU, job skips with a friendly message and passes.

### Governor Verification

- Purpose: Verify OFFLOAD bandwidth governor caps per tick.
- Run:
  ```powershell
  python scripts/governor_verify.py --server http://localhost:9001 --cap-gbps 10 --ticks 10 --tick-ms 200
  ```
- Expected: measured transfers respect cap within small slack.

### Apply Toggle

- The QuickView header offers an "Enable Apply" checkbox. When off:
  - `/autopilot/plan` returns a plan but does not execute it; check `GET /apply/last` for status.
  - You can also set at startup: `$env:KVOPT_ALLOW_APPLY = "0"`.

---

## Maintainers: In-Process vLLM Hook Wiring

See Maintainers guide: [docs/maintainers/vllm-hooks.md](maintainers/vllm-hooks.md)

Use KV-OptKit’s in-process hooks to update telemetry and Engine Activity from real runtime events (no dev hooks needed). See:

- `kvopt/integrations/vllm/hooks.py` — reference wrapper (`VLLMHooks`) exposing:
  - `on_request_start/update/finish`
  - `on_block_alloc/free`
  - `on_page_move`
- `kvopt/adapters/vllm_adapter.py` — adapter API:
  - `VLLMAdapter.current()` to obtain the live adapter in-process
  - `record_undo_add_back(gb)` to record exact rollback deltas

### A. ASGI middleware around vLLM OpenAI server (request lifecycle)

```python
# run_vllm_with_kvopt.py
import uvicorn
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from vllm.entrypoints.openai.api_server import app as vllm_app

from kvopt.integrations.vllm.hooks import VLLMHooks
from kvopt.adapters.vllm_adapter import VLLMAdapter

adapter = VLLMAdapter.current() or VLLMAdapter(config={})
hooks = VLLMHooks(adapter)

class KVOptLifecycleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = f"req-{id(request)}"
        is_completion = request.url.path in ("/v1/completions", "/v1/chat/completions")
        try:
            if is_completion:
                prompt_tokens = 0
                try:
                    body = await request.json()
                    prompt = body.get("prompt") or (body.get("messages") or [])
                    prompt_tokens = len(str(prompt).split())
                except Exception:
                    pass
                hooks.on_request_start(req_id, prompt_tokens)
            resp: Response = await call_next(request)
            return resp
        finally:
            if is_completion:
                hooks.on_request_finish(req_id)

vllm_app.add_middleware(KVOptLifecycleMiddleware)

if __name__ == "__main__":
    uvicorn.run(vllm_app, host="0.0.0.0", port=8000, log_level="info")
```

### B. Memory/block events (allocator/BlockManager)

```python
# Inside your allocator or BlockManager
from kvopt.integrations.vllm.hooks import VLLMHooks
from kvopt.adapters.vllm_adapter import VLLMAdapter

_hooks = None

def _hooks_init():
    global _hooks
    if _hooks is None:
        ad = VLLMAdapter.current()
        if ad:
            _hooks = VLLMHooks(ad)

def on_block_allocated(req_id: str, num_bytes: int):
    _hooks_init()
    if _hooks:
        _hooks.on_block_alloc(req_id, num_bytes)

def on_block_freed(req_id: str, num_bytes: int):
    _hooks_init()
    if _hooks:
        _hooks.on_block_free(req_id, num_bytes)

def on_page_moved(req_id: str, num_bytes: int, src_tier: str, dst_tier: str):
    _hooks_init()
    if _hooks:
        _hooks.on_page_move(req_id, num_bytes, src_tier, dst_tier)
```

### C. Precise rollbacks

If your engine computes net HBM reduction for a plan step, record it for exact rollback:

```python
from kvopt.adapters.vllm_adapter import VLLMAdapter

ad = VLLMAdapter.current()
if ad:
    ad.record_undo_add_back(gb=0.125)  # add back 0.125 GB on rollback
```

After wiring, QuickView’s “Engine Activity” and `/metrics` counters will update from real events, and adapter rollbacks use event-based deltas.


---

## Phase 6: CPU A/B Demos

Phase 6 provides standardized CPU A/B comparisons using a simple vLLM CPU server plus KV‑OptKit, with optional LMCache via Redis. It includes 5 single scenarios and 3 A/B pairs, a reliable warm step, and a consistent Grafana experience with four dashboards in the `KV-OptKit` folder.

Full guide: [docs/README-phase6.md](README-phase6.md)

Quick links:

- Single scenarios runner: `scripts/demos/run_scenario.ps1`
- A/B runner: `scripts/demos/run_cpu_ab.ps1`
- Grafana (all scenarios): [http://localhost:3001/](http://localhost:3001/) (folder `KV-OptKit`)

---

## Phase 7: GPU Scaffolding

Phase 7 introduces a GPU-backed path using vLLM with a CUDA image plus full observability. It also provides a no‑GPU development mode so you can validate wiring on Windows without hardware.

### No‑GPU development path (SIM)

- Services: `kvopt`, `prometheus`, `grafana` (no `vllm`).
- Expected: Prometheus target `kvopt` is UP; vLLM target shows DOWN (expected). GPU/TTFT/LMCache panels show “No data”.

```powershell
$env:KVOPT_ADAPTER = "sim"
$env:UPSTREAM_VLLM_URL = ""

docker compose -f docker/demos/gpu/docker-compose.gpu.baseline.yaml `
  up -d --build --no-deps kvopt prometheus grafana

# Generate some traffic
1..100 | % {
  Invoke-RestMethod http://localhost:9001/healthz | Out-Null
  Invoke-RestMethod http://localhost:9001/v1/hw | Out-Null
  Invoke-RestMethod http://localhost:9001/v1/workload | Out-Null
  Invoke-RestMethod http://localhost:9001/v1/profile | Out-Null
}
```

Open:
- Prometheus: http://localhost:9090/targets
- Grafana: http://localhost:3000 (folder `KV-OptKit`, Phase 7 GPU dashboard)

### GPU validation path (vLLM)

Prereq: A host with an NVIDIA GPU (WSL2 GPU on Windows, native Linux, or cloud VM) and Docker + NVIDIA container runtime.

```powershell
# Build CUDA vLLM image (one-time)
docker build -f docker/Dockerfile.vllm_gpu_cuda -t kvopt/vllm-gpu:dev .

# Bring up baseline GPU stack (vLLM + KV-OptKit + Prometheus + Grafana)
docker compose -f docker/demos/gpu/docker-compose.gpu.baseline.yaml up -d --build

# Warm + short traffic
powershell -ExecutionPolicy Bypass -File scripts/demos/run_gpu_scenario.ps1 `
  -Compose docker/demos/gpu/docker-compose.gpu.baseline.yaml `
  -Scenario baseline_gpu -StayUp
```

Advisor + LMCache stack:

```powershell
docker compose -f docker/demos/gpu/docker-compose.gpu.advisor.lmcache.yaml up -d --build
powershell -ExecutionPolicy Bypass -File scripts/demos/run_gpu_scenario.ps1 `
  -Compose docker/demos/gpu/docker-compose.gpu.advisor.lmcache.yaml `
  -Scenario advisor_with_lmcache_gpu -StayUp
```

Dashboards:
- Phase 7 GPU dashboard: GPU Utilization, HBM Used/Util, TTFT/P95.
- LMCache panels (hits/misses/bytes) populate in the advisor+LMCache stack.

Troubleshooting:
- If Grafana port 3000 is in use, stop the conflicting container (e.g., `open-webui`) or change port mapping.
- If vLLM target is DOWN on a GPU host, ensure the compose stack is up and the CUDA image built successfully.

