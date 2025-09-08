# Phase 4: Observability Demo (Prometheus + Grafana)
#
# This script helps validate the observability stack locally.
# It does NOT start Docker for you; run the compose command below in a separate terminal:
#   docker compose -f docker/compose.yml --profile obs up -d
#
# Then start KV-OptKit in another terminal:
#   # Option A (CPU-only, vLLM demo sequences):
#   $env:KVOPT_ADAPTER = "vllm"
#   $env:KVOPT_DEMO_SEQS = "1"
#   $env:KVOPT_PORT = "9001"
#   python -m kvopt.server.main
#
#   # Option B (CPU-only, SIM):
#   $env:KVOPT_ADAPTER = "sim"; $env:KVOPT_PORT = "9001"; python -m kvopt.server.main
#
# Optionally enable Dev Hooks to simulate Engine Activity (alloc/move/free):
#   $env:KVOPT_DEV = "1"
#
param(
  [string]$Server = $env:KVOPT_SERVER
)
if (-not $Server) { $Server = "http://localhost:9001" }

Write-Host "[Phase4] Using server: $Server"

# Probe health endpoints
try {
  $h = Invoke-RestMethod -Uri "$Server/healthz" -Method GET -ErrorAction Stop
  Write-Host "healthz: $($h.status) | adapter=$($h.adapter)"
} catch { Write-Warning "healthz failed: $($_.Exception.Message)" }

# Scrape metrics and snapshot
try {
  $m = Invoke-WebRequest -Uri "$Server/metrics" -Method GET -ErrorAction Stop
  ($m.Content -split "`n" | Select-String "^kvopt_") | ForEach-Object { $_.ToString() } | Out-String | Write-Host
} catch { Write-Warning "metrics failed: $($_.Exception.Message)" }

try {
  $snap = Invoke-RestMethod -Uri "$Server/metrics/snapshot" -Method GET -ErrorAction Stop
  Write-Host "snapshot: " ($snap | ConvertTo-Json -Depth 4)
} catch { Write-Warning "snapshot failed: $($_.Exception.Message)" }

Write-Host ""
Write-Host "Next steps:"
Write-Host "- Open Grafana (default): http://localhost:3000/"
Write-Host "- Open Prometheus (default): http://localhost:9090/"
Write-Host "- Open QuickView: $Server/"
Write-Host "- If KVOPT_DEV=1, use Dev Hooks panel in QuickView or PowerShell Invoke-RestMethod to post alloc/move/free"
