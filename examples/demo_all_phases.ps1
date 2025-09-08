# All-Phases Demo Orchestrator (non-strict demo)
# Runs Phase 1 -> 4 by default. Phase 5 steps are optional flags.
# Ports: Server/QuickView=9001, Prometheus=9090, Grafana=3001

param(
  [string]$BaseUrl = "http://localhost:9001",
  [switch]$IncludeObs = $true,
  [switch]$IncludePhase5SIM = $false,
  [switch]$IncludePhase5VLLM = $false
)

Write-Host "[All-Phases Demo] Starting" -ForegroundColor Cyan

function Run-Step($name, [scriptblock]$sb) {
  Write-Host "`n=== $name ===" -ForegroundColor Yellow
  try { & $sb } catch { Write-Host ("[WARN] {0}: {1}" -f $name, $_) -ForegroundColor DarkYellow }
}

# Ensure server running (best-effort): if not reachable, instruct user
try {
  $health = (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/healthz" -TimeoutSec 3).Content | Out-String
  Write-Host "[Info] Server reachable at $BaseUrl" -ForegroundColor Green
} catch {
  Write-Host "[Hint] Start server: $env:KVOPT_ADAPTER=(sim|vllm) ; $env:KVOPT_PORT=9001 ; python -m kvopt.server.main" -ForegroundColor Yellow
}

# Phase 1
Run-Step "Phase 1: Advisor" {
  ./examples/demo_phase1_advisor.ps1
}

# Phase 2
Run-Step "Phase 2: Autopilot" {
  ./examples/demo_phase2_autopilot.ps1
}

# Phase 3
Run-Step "Phase 3: Governor" {
  ./examples/demo_phase3_governor.ps1
}

# Phase 4 (Observability)
if ($IncludeObs) {
  Run-Step "Phase 4: Observability" {
    Write-Host "Open UIs:" -ForegroundColor Green
    Write-Host "  QuickView : http://localhost:9001/"
    Write-Host "  Prometheus: http://localhost:9090/"
    Write-Host "  Grafana   : http://localhost:3001/"
    try {
      (Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:9090/api/v1/status/runtimeinfo" -TimeoutSec 5) | Out-Null
      Write-Host "Prometheus is up." -ForegroundColor Green
    } catch { Write-Host "Prometheus not reachable (optional)." -ForegroundColor Yellow }
  }
}

# Phase 5 (optional)
if ($IncludePhase5SIM) {
  Run-Step "Phase 5.A: SIM quickflow" {
    Write-Host "Start SIM server if needed and use Phase 5.A demo." -ForegroundColor Green
    Write-Host "See docs: Phase 5.A section."
  }
}
if ($IncludePhase5VLLM) {
  Run-Step "Phase 5.B/5.C: vLLM demo + Sidecar" {
    Write-Host "Start vLLM demo/sidecar per guide. This orchestrator leaves GPU steps manual on purpose." -ForegroundColor Green
  }
}

Write-Host "`n[All-Phases Demo] Done" -ForegroundColor Cyan
