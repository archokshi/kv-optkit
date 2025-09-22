# Horizontal Phase HP1: Discovery
## Quick Verify

Run these one-liners in PowerShell to validate HP1 endpoints on the default port 9001.

```powershell
Invoke-RestMethod http://localhost:9001/healthz    | ConvertTo-Json -Depth 4
Invoke-RestMethod http://localhost:9001/v1/hw      | ConvertTo-Json -Depth 4
Invoke-RestMethod http://localhost:9001/v1/workload| ConvertTo-Json -Depth 4
Invoke-RestMethod http://localhost:9001/v1/profile | ConvertTo-Json -Depth 4
```

If you see JSON responses for each, HP1 is healthy.

---

## Where to go next

- Phase 6 (CPU A/B demos): see `docs/README-phase6.md`
- Phase 7 (GPU scaffolding): see `docs/README-phase7.md`

---

## Validate HP1 (Windows PowerShell)

Ensure the server is running (or use the CLI helpers without the server).

Start server on port 9001:

```powershell
$env:KVOPT_PORT = "9001"
python -m kvopt.server.main
```

In a new terminal, verify routes include HP1:

```powershell
Invoke-RestMethod -Uri http://localhost:9001/debug/routes | ConvertTo-Json -Depth 6
```

Query discovery endpoints:

```powershell
# Full HW; then memory and network sections
Invoke-RestMethod -Uri http://localhost:9001/v1/hw | ConvertTo-Json -Depth 8
(Invoke-RestMethod -Uri http://localhost:9001/v1/hw).memory  | ConvertTo-Json -Depth 8
(Invoke-RestMethod -Uri http://localhost:9001/v1/hw).network | ConvertTo-Json -Depth 8

# Workload (env defaults). Optionally set $env:PROMETHEUS_URL to auto-hint.
Invoke-RestMethod -Uri http://localhost:9001/v1/workload | ConvertTo-Json -Depth 6

# Profile decision (includes rationale and compatibility)
Invoke-RestMethod -Uri http://localhost:9001/v1/profile | ConvertTo-Json -Depth 8
```

CLI (no server required):

```powershell
# First time only (inside repo): install in editable mode
./.venv/Scripts/pip.exe install -e .

# HP1 helpers
python -m kvopt.cli.main hp1 hw
python -m kvopt.cli.main hp1 workload
python -m kvopt.cli.main hp1 profile
python -m kvopt.cli.main hp1 plan   # add --apply to execute docker pull/build
```

---

## Troubleshooting

- Port in use (bind error on 9001):
  - `netstat -ano | findstr :9001` → find PIDs; then `taskkill /PID <PID> /F` or stop Docker stacks mapping 9001.
  - Or run on another port: set `$env:KVOPT_PORT = "9101"`.

- psutil not installed (memory/network null):
  - `./.venv/Scripts/pip.exe install psutil` and restart the server with the venv’s python.

- CLI import error after edits:
  - `./.venv/Scripts/pip.exe uninstall -y kv-optkit`
  - `./.venv/Scripts/pip.exe install -e .`

- Prometheus auto-hints not active:
  - Ensure Docker Desktop is running, then `docker compose -f docker/compose.yml --profile obs up -d`.
  - Set `$env:PROMETHEUS_URL = "http://localhost:9090"` and re-run `/v1/workload` or `hp1 workload`.


This Horizontal Phase runs before every other phase. It detects the host capabilities (hardware + runtime), infers a workload profile, and resolves a compatible software stack and runtime profile. Results are exposed via API and used by demo scripts, CI, and production deployments.

---

## Goals

- Produce an authoritative hardware capability profile.
- Infer an initial workload profile (SLO hints, model footprint, cache pressure).
- Resolve a compatible stack: CUDA/Torch/vLLM/LMCache versions or CPU fallback.
- Select a runtime profile and initial tuning (model/context, LMCache tier budgets, governors).
- Provide a safe provisioning plan (containers only; never install host drivers).

---

## Scope (What is discovered)

- CPU: sockets, cores, NUMA, SIMD flags.
- GPU: count, name, VRAM, SM/compute capability, MIG mode, driver, CUDA compat.
- Memory/Storage: DRAM total/free, HBM (via GPUs), local NVMe size, optional external memory (PCIe/CXL) if detectable.
- Networking: NIC type, link speed, basic RTT/bandwidth probes to configured backends.
- Runtime: OS, Docker, NVIDIA Container Toolkit, kernel/cgroups, container limits.

Outputs are normalized into a structured JSON profile.

---

## Public APIs (Server)

- `GET /v1/hw` – Hardware capability profile.
- `GET /v1/workload` – Workload profile (config + recent metrics if available).
- `GET /v1/profile` – Chosen runtime profile, compatibility resolution, and tuning decisions.

---

## Files and Modules (Implementation Plan)

- `kvopt/system/hw.py` – Hardware discovery.
- `kvopt/system/workload.py` – Workload profile inference.
- `kvopt/system/profile.py` – Compatibility resolver + runtime profile selector.
- `kvopt/system/provision.py` – Safe provisioning planner (containers only).
- `kvopt/server/routes_hw.py` – Implements `/v1/hw`, `/v1/workload`, `/v1/profile`.
- `config/compatibility.yaml` – Driver ↔ CUDA ↔ Torch+CUDA ↔ vLLM ↔ LMCache mapping.
- `config/runtime_profiles.yaml` – Definitions: `cpu_simple`, `gpu_vllm_native`, `gpu_vllm_lmcache_native`, `gpu_autopilot_lmcache`, `ext_memory_pcie_cxl`.
- `config/kvopt.yaml` – Central budgets/policy/routing/SLOs (overridable via env flags).
- Optional CLI helpers:
  - `kvopt hw show`, `kvopt profile plan`, `kvopt provision --dry-run|--apply`.

---

## Safe Provisioning (Guardrails)

- `kvopt provision --dry-run` prints exact steps (pull CUDA base, build images, validate toolkit).
- `kvopt provision --apply` executes container pulls/builds only.
- Never auto-install host drivers/toolkits; provide links/instructions instead.

---

## How Other Phases Use HP1

- Demo scripts read `/v1/profile` to pick compose files and labels automatically.
- Autopilot/Advisor size models and LMCache budgets from `/v1/hw`.
- CI uses `/v1/hw` to route jobs (CPU vs GPU lanes) and assert expected metrics.
- Phase 6 (CPU) and Phase 7 (GPU) remain unchanged; they simply consume HP1 outputs.

---

## Exit Criteria

1) Discovery accuracy across environments
- `/v1/hw` returns correct data on:
  - CPU-only host
  - Bare-metal NVIDIA GPU host
  - At least one GPU cloud (CoreWeave, Lambda, AWS/GCP/Azure)

2) Profile resolution & fallbacks
- `/v1/profile` picks a compatible stack or emits a clear fallback with remediation steps.
- Logs include rationale: chosen CUDA base, Torch+CUDA wheels, vLLM, LMCache, model/context sizing, LMCache tier budgets.

3) Provisioning
- `kvopt provision --dry-run` and `--apply` succeed (containers only) on CPU and GPU hosts.

4) Documentation & UX
- This document exists and is referenced from the main demo guide.
- Example outputs for common hosts are provided (appendix to be added when implemented).

---

## Compatibility Guarantees

- HP1 is non-invasive and backward compatible.
- Existing phases (1–6) continue to work without HP1, but when HP1 is present they gain auto-configuration.
- Future phases can rely on HP1 contracts (`/v1/hw`, `/v1/workload`, `/v1/profile`) to remain environment-agnostic.

---

## Future Extensions

- Microbench probes to refine bandwidth/latency estimates (DRAM/NVMe/NIC).
- Vendor-specific enrichment for PCIe/CXL external memory.
- Persist profiles and decisions for audit/repro in `outputs/`.
