param(
  [switch]$StayUp
)

$ErrorActionPreference = "Stop"

$baseline = "docker/demos/gpu/docker-compose.gpu.baseline.yaml"
$advisor  = "docker/demos/gpu/docker-compose.gpu.advisor.lmcache.yaml"

function Invoke-Scenario($compose, $scenario) {
  Write-Host "[KVOPT] Running scenario: $scenario" -ForegroundColor Cyan
  & powershell -ExecutionPolicy Bypass -File "scripts/demos/run_gpu_scenario.ps1" -Compose $compose -Scenario $scenario -StayUp
}

Invoke-Scenario $baseline "baseline_gpu"
Invoke-Scenario $advisor  "advisor_with_lmcache_gpu"

if (-not $StayUp) {
  docker compose -f $baseline down -v
  docker compose -f $advisor down -v
}
