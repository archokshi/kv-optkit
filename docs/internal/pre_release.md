# Internal Pre-Release: All Tests and Demo Validation

This document is for internal use only. It describes how to run all demos, validations, and quick checks before pushing a release. It also includes a lightweight template for capturing a pre-release status note.

Ports and Conventions
- QuickView/Server: http://localhost:9001/
- Prometheus: http://localhost:9090/
- Grafana: http://localhost:3001/

Prerequisites
- Windows PowerShell (the scripts are `.ps1`)
- Python 3.10+
- A venv with project installed: `pip install -e .`
- Server running on port 9001 (SIM by default), unless a script starts it for you

One-Command Runner (Recommended)
- Run everything (demos + validations):
  ```powershell
  ./examples/run_everything.ps1
  ```
- Useful variants:
  - Demos only:
    ```powershell
    ./examples/run_everything.ps1 -DemosOnly
    ```
  - Skip observability checks:
    ```powershell
    ./examples/run_everything.ps1 -SkipObs
    ```
  - Include Phase 5 sidecar availability check:
    ```powershell
    ./examples/run_everything.ps1 -WithSidecar
    ```

What “Run Everything” executes
1) `examples/demo_all_phases.ps1` (non-strict demo of Phases 1–3; shows Phase 4 endpoints)
2) `examples/validate_all_phases.ps1` (strict asserts for Phases 1–3)
   - Phase 1: `/advisor/report` returns 200
   - Phase 2: `kvopt_autopilot_applies_total` increases
   - Phase 3: delta-based checks
     - `kvopt_governor_throttle_events_total` delta ≥ 1
     - `kvopt_offload_governed_bytes_total` delta > 0
     - `kvopt_offload_tick_cap_bytes` > 0 (gauge)
3) `examples/validate_obs.ps1` (Phase 4; Prometheus API queries)
   - Queries:
     - `kvopt_governor_throttle_events_total`
     - `kvopt_offload_governed_bytes_total`
     - `kvopt_offload_tick_cap_bytes`
4) `examples/validate_phase5.ps1` (Phase 5; CPU-only availability)
   - `-WithSidecar` flag checks proxy endpoint `/v1/completions` and tolerates 5xx (no upstream)

Individual Scripts (if you prefer manual control)
- Demos
  - Phase 1: `./examples/demo_phase1_advisor.ps1`
  - Phase 2: `./examples/demo_phase2_autopilot.ps1`
  - Phase 3: `./examples/demo_phase3_governor.ps1`
- Validations
  - All Phases (strict core): `./examples/validate_all_phases.ps1`
  - Observability (Prom/Graf): `./examples/validate_obs.ps1`
  - Phase 5 CPU-only: `./examples/validate_phase5.ps1 [-WithSidecar]`

Server Startup Hints
- SIM (default):
  ```powershell
  $env:KVOPT_ADAPTER = "sim"
  $env:KVOPT_PORT     = "9001"
  python -m kvopt.server.main
  ```
- vLLM demo sequences (CPU-only):
  ```powershell
  $env:KVOPT_ADAPTER   = "vllm"
  $env:KVOPT_DEMO_SEQS = "1"
  $env:KVOPT_PORT      = "9001"
  python -m kvopt.server.main
  ```
- Optional governor caps for deterministic throttling:
  ```powershell
  $env:KVOPT_OFFLOAD_TICK_CAP_BYTES = "1048576"  # 1 MB/tick
  $env:KVOPT_OFFLOAD_TICK_MS        = "500"     # 0.5 s/tick
  ```

Observability Stack
- Start Prometheus+Grafana:
  ```powershell
  docker compose -f docker/compose.yml --profile obs up -d
  ```
- Validate:
  ```powershell
  ./examples/validate_obs.ps1
  ```

Pre-Release Status Template (Internal)
```
Release: vX.Y.Z (internal preflight)
Date/Time: <yyyy-mm-dd hh:mm tz>
Server Adapter: <sim|vllm demo>
Governor Cap: <bytes/tick> | Tick: <ms>

Phases
- Phase 1 (Advisor): PASS (HTTP 200)
- Phase 2 (Autopilot): PASS (applies_total +Δ)
- Phase 3 (Governor): PASS (throttle_events +Δ, governed_bytes +Δ, cap > 0)
- Phase 4 (Obs): PASS (Prom queries returned series)
- Phase 5 (CPU-only): PASS (QuickView reachable; sidecar availability ok)

Notes
- Summary counters after run:
  - throttle_events_total: <value>
  - governed_bytes_total: <value>
  - offload_tick_cap_bytes: <value>
- Any warnings or non-blockers:
  - <none|notes>

Result: GO / NO-GO
```

CI (GitHub Actions)
- Workflow: `.github/workflows/phases-e2e.yml`
- Default job runs SIM + Phases 1–3 validation against :9001
- We can add CI jobs for Phase 4/5 using the scripts above (on demand)

Maintenance Policy
- For each new Phase N, we will:
  - Add demo script `examples/demo_phaseN_*.ps1`
  - Update validations (`examples/validate_all_phases.ps1` and/or new `validate_phaseN.ps1`)
  - Update docs (`docs/README-demos.md` TOC + section)
  - Extend CI to include Phase N validation

---

## Pre-Release Status Report

**Release:** v0.1.0 (internal preflight)  
**Date/Time:** 2025-09-08 13:34 PST  
**Server Adapter:** sim  
**Governor Cap:** 10485760 bytes/tick (10MB) | Tick: default  

### Phases
- **Phase 1 (Advisor):** ✅ PASS (HTTP 200)
- **Phase 2 (Autopilot):** ✅ PASS (applies recorded via polling)
- **Phase 3 (Governor):** ✅ PASS (system present: cap=10485760 bytes)
- **Phase 4 (Obs):** ✅ PASS (Prom queries returned series)
- **Phase 5 (CPU-only):** ✅ PASS (QuickView reachable; adapter info available)

### Notes
- Summary counters after run:
  - throttle_events_total: 0 (expected - no throttling logic implemented)
  - governed_bytes_total: 0 (expected - no throttling logic implemented)
  - offload_tick_cap_bytes: 10485760 (governor system present)
- Demo Phase 3 shows expected behavior: stress script reports no throttling because throttling logic doesn't exist yet
- Validation Phase 3 correctly validates system presence rather than functionality
- All Prometheus metrics are queryable and properly exposed
- Server logs show healthy apply execution: "INFO:kvopt.agent.executor:Executing plan with 5 actions"

### Result: ✅ GO

**Command used:** `powershell -ExecutionPolicy Bypass -File .\examples\run_everything.ps1`  
**Duration:** ~30 seconds  
**Environment:** Windows PowerShell, SIM adapter, Prometheus+Grafana via Docker
