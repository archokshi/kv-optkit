# Phase 6: CPU A/B Demo Guide

This guide shows how to run the five single CPU scenarios and the three A/B comparisons using the standardized CPU stack (simple vLLM server + KV‑OptKit + optional LMCache plugin via Redis).

All scenarios provision the same four Grafana dashboards and expose the same ports:
- Grafana: http://localhost:3001
- Prometheus: http://localhost:9090
- KV‑OptKit: http://localhost:9001
- vLLM (simple): http://localhost:8000

Dashboards (appear under the folder "KV-OptKit"):
- KV‑OptKit Phase 6 Dashboard
- KV‑OptKit Phase 6 A/B (CPU)
- KV‑OptKit All Phases (1–6)
- KV‑OptKit

## Prerequisites
- Windows PowerShell
- Python 3.10+
- Project dependencies installed in your virtual environment
- Docker Desktop running

## Warm/Validation Expectations
Each run performs a warm step that validates:
- vLLM endpoint is reachable at `/v1/models`
- KV‑OptKit `/metrics` is served
- End‑to‑end request path works before generating traffic

The CPU scenarios use `Dockerfile.vllm_cpu_simple`, which is reliable on CPU. LMCache is enabled via KV‑OptKit plugin when requested, using Redis.

---

## Single Scenarios (run_scenario.ps1)
`scripts/demos/run_scenario.ps1` starts one scenario, warms it, generates traffic loops, and optionally keeps it running for observation.

Common flags:
- `-WarmCount <N>` number of warm requests (default 20)
- `-WarmInterval <sec>` delay between warm requests (default 0.3)
- `-TrafficLoops <N>` number of loops (default 60)
- `-TrafficCount <N>` requests per loop (default 10)
- `-TrafficInterval <sec>` delay between requests (default 0.5)
- `-StayUp` keep containers running for manual stop later

### 1) Baseline (no plugins)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_scenario.ps1 -Scenario baseline -StayUp
```

### 2) Advisor without LMCache
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_scenario.ps1 -Scenario advisor_without_lmcache -StayUp
```

### 3) Advisor with LMCache (Redis backend)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_scenario.ps1 -Scenario advisor_with_lmcache -StayUp
```

### 4) LMCache only
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_scenario.ps1 -Scenario lmcache_only -StayUp
```

### 5) Autopilot with LMCache
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_scenario.ps1 -Scenario autopilot_with_lmcache -StayUp
```

Manual stop when done observing:
```powershell
# baseline
docker compose -f docker/demos/cpu/docker-compose.cpu.baseline.yaml down
# advisor_without_lmcache
docker compose -f docker/demos/cpu/docker-compose.cpu.advisor.nocache.yaml down
# advisor_with_lmcache
docker compose -f docker/demos/cpu/docker-compose.cpu.advisor.lmcache.yaml down
# lmcache_only
docker compose -f docker/demos/cpu/docker-compose.cpu.lmcache.only.yaml down
# autopilot_with_lmcache
docker compose -f docker/demos/cpu/docker-compose.cpu.autopilot.lmcache.yaml down
```

---

## A/B Scenarios (run_cpu_ab.ps1)
`scripts/demos/run_cpu_ab.ps1` brings up scenario A, validates and warms, generates traffic with a phase label, and then repeats for scenario B. Use `-StayUp` to keep stacks running for manual stop.

Common flags:
- `-WarmCount 20 -WarmInterval 0.3`
- `-AutoCount 60 -AutoInterval 0.5`
- `-StayUp` (recommended for observation)

The script auto‑opens the Phase 6 A/B dashboard:
- http://localhost:3001/d/kvopt-ab-cpu/kv-optkit-phase-6-a-b-cpu

Labels applied for comparison are derived from the scenario name (e.g., `baseline_cpu`, `advisor_without_lmcache_cpu`, etc.). Use these labels in the dashboards to compare A vs B within one Grafana instance.

### A) Baseline vs Advisor without LMCache
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_cpu_ab.ps1 `
  -A baseline.cpu `
  -B advisor_without_lmcache.cpu `
  -WarmCount 20 -WarmInterval 0.3 `
  -AutoCount 60 -AutoInterval 0.5 `
  -StayUp
```

### B) Advisor with LMCache vs LMCache only
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_cpu_ab.ps1 `
  -A advisor_with_lmcache.cpu `
  -B lmcache_only.cpu `
  -WarmCount 20 -WarmInterval 0.3 `
  -AutoCount 60 -AutoInterval 0.5 `
  -StayUp
```

### C) LMCache only vs Autopilot with LMCache
```powershell
powershell -ExecutionPolicy Bypass -File scripts/demos/run_cpu_ab.ps1 `
  -A lmcache_only.cpu `
  -B autopilot_with_lmcache.cpu `
  -WarmCount 20 -WarmInterval 0.3 `
  -AutoCount 60 -AutoInterval 0.5 `
  -StayUp
```

Manual stop when done observing:
```powershell
# baseline.cpu
docker compose -f docker/demos/cpu/docker-compose.cpu.baseline.yaml down
# advisor_without_lmcache.cpu
docker compose -f docker/demos/cpu/docker-compose.cpu.advisor.nocache.yaml down
# advisor_with_lmcache.cpu
docker compose -f docker/demos/cpu/docker-compose.cpu.advisor.lmcache.yaml down
# lmcache_only.cpu
docker compose -f docker/demos/cpu/docker-compose.cpu.lmcache.only.yaml down
# autopilot_with_lmcache.cpu
docker compose -f docker/demos/cpu/docker-compose.cpu.autopilot.lmcache.yaml down
```

---

## Dashboards
Open Grafana and select folder `KV-OptKit`:
- `KV-OptKit Phase 6 Dashboard` – Core CPU metrics and activity
- `KV-OptKit Phase 6 A/B (CPU)` – A/B comparison view (TTFT, requests, applies, apply success/fail)
- `KV-OptKit All Phases (1–6)` – Overview across all demo phases
- `KV-OptKit` – Catch‑all, comprehensive dashboard

If dashboards don’t appear immediately:
1. Restart Grafana for the active compose file to reload provisioning:
   ```powershell
   docker compose -f <compose-file> restart grafana
   ```
2. If needed, `down` then `up -d` the stack once.
3. Hard refresh the browser (Ctrl+F5) on http://localhost:3001.

---

## Troubleshooting
- Port busy errors when running multiple stacks: stop any previous stack before starting the next. Only one Grafana/Prometheus should run on the host ports at a time.
- Warm failure for vLLM: ensure the scenario uses the simple CPU server and no other process is bound to port 8000.
- No dashboards: verify the Grafana container mounts:
  - `docker/grafana/provisioning/datasources` → `/etc/grafana/provisioning/datasources`
  - `docker/grafana/provisioning/dashboards` → `/etc/grafana/provisioning/dashboards`
  - `docker/grafana/dashboards` → `/var/lib/grafana/dashboards`
- Last resort: recreate Grafana with `down -v` (removes the local Grafana DB) and start again; dashboards will re‑provision from JSON files.

---

## Notes
- LMCache on CPU is provided through the KV‑OptKit plugin with Redis. The simple vLLM server is used to ensure warm validation and inference piping works reliably in CPU environments.
- All metrics panels expect Prometheus scraping from `kvopt` and `vllm` containers.

---

## Screenshot Checklist (Phase 6 Evidence)

Use the dashboards in folder `KV-OptKit` and save screenshots under `docs/images/phase6/`.

- TTFT comparison from `KV-OptKit Phase 6 A/B (CPU)`
  - Time range: Last 30 minutes; Refresh: 5–10s
  - Labels to compare: `baseline_cpu`, `advisor_without_lmcache_cpu`, `advisor_with_lmcache_cpu`, `lmcache_only_cpu`, `autopilot_with_lmcache_cpu`
- P95 latency comparison (target within ±3% of baseline)
- Apply Success/Fail totals (both phases)
- Autopilot Applies totals (both phases)
- Optional: LMCache panels (Hit Rate, Hits/Misses, Bytes Warmed/Recalled) for LMCache scenarios

Tip: If dashboards don’t appear or look empty, restart Grafana for the active compose file:

```powershell
docker compose -f <compose-file> restart grafana
```

## Prometheus Queries (for Screenshots)

These are the exact expressions used by the dashboards in `docker/grafana/dashboards/`:

- TTFT (ms)
  - `kvopt_ttft_ms`
- HTTP Requests by path (1m rate)
  - `sum by (path)(rate(http_requests_total[1m]))`
- Autopilot Applies total
  - `kvopt_autopilot_applies_total`
- Apply Success/Fail total
  - `kvopt_apply_success_total`
  - `kvopt_apply_fail_total`
- LMCache Hit Rate (5m)
  - `clamp_min(rate(kvopt_lmcache_hits_total[5m]) / (rate(kvopt_lmcache_hits_total[5m]) + rate(kvopt_lmcache_misses_total[5m])), 0) or on() vector(0)`
- LMCache Hits/Misses (1m rate)
  - `clamp_min(rate(kvopt_lmcache_hits_total[1m]),0) or on() vector(0)`
  - `clamp_min(rate(kvopt_lmcache_misses_total[1m]),0) or on() vector(0)`
- LMCache Bytes: Warmed/Recalled (1m rate)
  - `clamp_min(rate(kvopt_lmcache_bytes_warmed_total[1m]),0) or on() vector(0)`
  - `clamp_min(rate(kvopt_lmcache_bytes_recalled_total[1m]),0) or on() vector(0)`

Notes:
- HBM panels will read zero on CPU-only runs; this is expected.
- If you run multiple stacks concurrently, ensure only one Prometheus/Grafana pair is bound to host ports.

---

## Proposed Next Steps (Phase 6 Closure)

Use this checklist to finalize Phase 6 and collect evidence.

- Validation & Evidence

  - Run the three A/B pairs via `scripts/demos/run_cpu_ab.ps1` with `-StayUp`.
  - Capture screenshots in `docs/images/phase6/` showing:
    - TTFT improvements (target 2–5×) from the A/B dashboard.
    - P95 latency within ±3% of baseline.
    - Apply Success/Fail and Autopilot Applies panels for both phases.
  - Include Prometheus queries as text notes for reproducibility.

- Tests (Unit/Integration)

  - Governors enforcement (OFFLOAD, PREFETCH) including throttle metrics.
  - Planner ordering and stop‑early behavior; REUSE→EVICT→OFFLOAD→PREFETCH→QUANTIZE.
  - Idempotent apply/rollback flow (txn log).
  - LMCache provider metrics for bytes offloaded/prefetched.

- CI Matrix Extension

  - Ensure `.github/workflows/conformance.yml` runs nightly at midnight PST and on PRs.
  - Matrix axes:
    - Python: 3.10, 3.11
    - Plugin channel: `latest`, `fallback`
  - CPU‑only mode on in CI to avoid CUDA installs.

- Runtime Denylist (Safety Fallback)

  - Use `KVOPT_PLUGIN_DENYLIST` to disable problematic providers by name.
  - Optionally surface a banner in QuickView indicating degraded (Advisor‑only) mode when denylist is active.

- Unified Config + CLI

  - Centralize budgets/policy/routing/SLO in `config/kvopt.yaml`.
  - CLI commands:
    - `kvopt plugin ls|enable|disable`
    - `kvopt autopilot on` (or server route)

- Troubleshooting Tips

  - If dashboards do not appear, restart Grafana for the active compose stack:

    ```powershell
    docker compose -f <compose-file> restart grafana
    ```

  - If warm fails for vLLM in CPU demos, ensure the simple CPU server is used and port 8000 is free.
  - If multiple stacks are running, stop old Grafana/Prometheus to free ports.

