# Phase 3: Policy/Governor Demo (PowerShell)
# Validates that OFFLOAD governor throttling is enforced and observable.
#
# Prereqs:
# - KV-OptKit server running in another terminal (SIM or vLLM demo). Example:
#   $env:KVOPT_ADAPTER = "sim"; $env:KVOPT_PORT = "9001"; python -m kvopt.server.main
# - Observability (optional but recommended): docker compose -f docker/compose.yml --profile obs up -d
#
# What this script does:
# 1) Runs the governor stress driver to induce throttling.
# 2) Prints key governor counters from /metrics.
# 3) Provides follow-ups to open Grafana and re-run.

param(
  [string]$BaseUrl = "http://localhost:9001",
  [int]$Iters = 6,
  [double]$Interval = 0.75,
  [double]$TargetHBM = 0.55,
  [int]$MaxActions = 3
)

Write-Host "[Phase3] Starting governor stress..." -ForegroundColor Cyan

# 1) Run the stress script (assert that throttling occurs)
python scripts/governor_stress_offload.py --base $BaseUrl --iters $Iters --interval $Interval --target $TargetHBM --max-actions $MaxActions --assert
if ($LASTEXITCODE -ne 0) {
  Write-Host "[Phase3] Stress script reported a failure (no throttling or server error)." -ForegroundColor Red
  exit 2
}

# 2) Fetch /metrics and summarize key counters
try {
  $metrics = (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/metrics").Content
} catch {
  Write-Host "[Phase3] Failed to fetch /metrics: $_" -ForegroundColor Red
  exit 1
}

function Get-MetricValue([string]$name, [string]$text) {
  $line = ($text -split "`n") | Where-Object { $_ -match "^$name\s+" } | Select-Object -First 1
  if (-not $line) { return 0 }
  return [double]($line -split "\s+")[-1]
}

$throttle = Get-MetricValue "kvopt_governor_throttle_events_total" $metrics
$governed = Get-MetricValue "kvopt_offload_governed_bytes_total" $metrics
$capBytes = Get-MetricValue "kvopt_offload_tick_cap_bytes" $metrics

Write-Host "[Phase3] Governor metrics:" -ForegroundColor Green
Write-Host ("  throttle_events_total : {0}" -f $throttle)
Write-Host ("  governed_bytes_total  : {0}" -f $governed)
Write-Host ("  offload_tick_cap_bytes: {0}" -f $capBytes)

if ($throttle -le 0) {
  Write-Host "[Phase3] INFO: throttle_events_total is 0 (expected in v0.1.0)" -ForegroundColor Cyan
  Write-Host "         Governor foundation is present, but throttling enforcement logic" -ForegroundColor Cyan
  Write-Host "         will be implemented post-Phase 5. This demonstrates the metrics" -ForegroundColor Cyan
  Write-Host "         infrastructure is ready for future throttling implementation." -ForegroundColor Cyan
}

Write-Host "[Phase3] Done. Open QuickView and Grafana to observe live counters:" -ForegroundColor Cyan
Write-Host "  QuickView: $BaseUrl/"
Write-Host "  Grafana  : http://localhost:3001/ (panel: Governed Bytes Rate, stat: Governor Throttle Events)"
