# Run Everything: demos then validations
# Ports: Server/QuickView=9001, Prometheus=9090, Grafana=3001
# Usage examples:
#   ./examples/run_everything.ps1                      # demos + validations (Phases 1-3) + obs check
#   ./examples/run_everything.ps1 -SkipObs             # skip Prom/Grafana checks
#   ./examples/run_everything.ps1 -WithSidecar         # include Phase 5 sidecar availability check
#   ./examples/run_everything.ps1 -DemosOnly           # only demos, no validations

param(
  [string]$BaseUrl = "http://localhost:9001",
  [switch]$DemosOnly = $false,
  [switch]$SkipObs = $false,
  [switch]$WithSidecar = $false
)

$ErrorActionPreference = 'Stop'

function Run-Step($name, [scriptblock]$sb) {
  Write-Host "`n=== $name ===" -ForegroundColor Yellow
  & $sb
}

# Ensure server hints (best effort)
try { (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/healthz" -TimeoutSec 5) | Out-Null } catch { Write-Host "[Hint] Start server: $env:KVOPT_ADAPTER=(sim|vllm); $env:KVOPT_PORT=9001; python -m kvopt.server.main" -ForegroundColor DarkYellow }

# 1) Demos
Run-Step "Demos: All Phases (non-strict)" { ./examples/demo_all_phases.ps1 }

if (-not $DemosOnly) {
  # 2) Validations (strict)
  Run-Step "Validate: Phases 1-3" { ./examples/validate_all_phases.ps1 -BaseUrl $BaseUrl -ValidateObs:(!$SkipObs) }
  if (-not $SkipObs) {
    Run-Step "Validate: Phase 4 Observability" { ./examples/validate_obs.ps1 -Server $BaseUrl }
  }
  # Phase 5 (CPU-only, availability checks)
  Run-Step "Validate: Phase 5 (CPU-only)" { ./examples/validate_phase5.ps1 -Server $BaseUrl -WithSidecar:$WithSidecar }
}

Write-Host "`n[Run Everything] Completed." -ForegroundColor Green
