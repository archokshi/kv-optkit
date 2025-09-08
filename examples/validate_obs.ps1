# Phase 4 Observability Validation (Prometheus+Grafana)
# Assumes docker compose obs stack is running and server is on :9001.
# Ports: Prometheus=9090, Grafana=3001

param(
  [string]$Prom = "http://localhost:9090",
  [string]$Server = "http://localhost:9001"
)

$ErrorActionPreference = 'Stop'

function Invoke-Json($url) {
  $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 10
  if (-not ($r.StatusCode -eq 200)) { throw "HTTP $($r.StatusCode): $url" }
  return ($r.Content | ConvertFrom-Json)
}

Write-Host "[Obs] Checking Prometheus readiness..." -ForegroundColor Cyan
$ready = Invoke-WebRequest -UseBasicParsing -Uri "$Prom/-/ready" -TimeoutSec 10
if ($ready.StatusCode -ne 200) { throw "Prometheus not ready" }

# Ensure server metrics export is reachable
Write-Host "[Obs] Checking server /metrics..." -ForegroundColor Cyan
$metricsText = (Invoke-WebRequest -UseBasicParsing -Uri "$Server/metrics" -TimeoutSec 10).Content
if (-not $metricsText) { throw "/metrics empty" }

# Query a few key metrics via Prometheus API
$queries = @(
  'kvopt_governor_throttle_events_total',
  'kvopt_offload_governed_bytes_total',
  'kvopt_offload_tick_cap_bytes'
)

foreach ($q in $queries) {
  $resp = Invoke-Json "$Prom/api/v1/query?query=$([uri]::EscapeDataString($q))"
  if ($resp.status -ne 'success') { throw "Prom query failed: $q" }
  $result = $resp.data.result
  if ($result.Count -lt 1) { throw "Prom found no series for: $q" }
  Write-Host "[Obs] OK $q -> $(($result | ConvertTo-Json -Compress))" -ForegroundColor Green
}

Write-Host "[Obs] Observability validation passed." -ForegroundColor Green
