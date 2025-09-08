# Phase 5.A: CPU-only — SIM (L3 End-to-End)
# Assumes KV-OptKit server is running separately with:
#   $env:KVOPT_ADAPTER = "sim"; $env:KVOPT_PORT = 9001; python -m kvopt.server.main

$Server = $env:KVOPT_SERVER
if (-not $Server) { $Server = "http://localhost:9001" }

Write-Host "[Phase5.A] Using server: $Server"

# Check status
Invoke-RestMethod -Uri "$Server/server/status" -Method GET | Format-List | Out-String | Write-Host

# Advisor report
$rep = Invoke-RestMethod -Uri "$Server/advisor/report" -Method GET
Write-Host "Advisor recommendations: $($rep.recommendations.Count)"

# Ensure Apply is enabled (server toggle)
Invoke-RestMethod -Uri "$Server/server/allow_apply" -Method POST -Body (@{allow=$true} | ConvertTo-Json) -ContentType "application/json" | Out-Null

# Apply a plan (non-dry-run)
$payload = @{ target_hbm_util = 0.75; max_actions = 3; priority = "medium"; allowed_actions = @("EVICT","OFFLOAD","QUANTIZE"); dry_run = $false } | ConvertTo-Json
$plan = Invoke-RestMethod -Uri "$Server/autopilot/plan" -Method POST -Body $payload -ContentType "application/json"
Write-Host "Applied plan: $($plan.plan_id)"

# Show guard + last apply + telemetry summaries
Invoke-RestMethod -Uri "$Server/guard/status" -Method GET | Format-List | Out-String | Write-Host
Invoke-RestMethod -Uri "$Server/apply/last" -Method GET | Format-List | Out-String | Write-Host
Invoke-RestMethod -Uri "$Server/telemetry" -Method GET | Format-List | Out-String | Write-Host
