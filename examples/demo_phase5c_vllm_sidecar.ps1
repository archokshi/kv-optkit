# Phase 5.C: CPU-only — vLLM Adapter + Sidecar Sequence Injection
# Assumes KV-OptKit server is running separately with:
#   $env:KVOPT_ADAPTER = "vllm"; $env:KVOPT_DEMO_SEQS = "0"; $env:KVOPT_PORT = 9001; python -m kvopt.server.main

$Server = $env:KVOPT_SERVER
if (-not $Server) { $Server = "http://localhost:9001" }

Write-Host "[Phase5.C] Using server: $Server"

# Status (should show adapter=vllm, demo_seqs=off)
Invoke-RestMethod -Uri "$Server/server/status" -Method GET | Format-List | Out-String | Write-Host

# Ensure Apply is enabled
Invoke-RestMethod -Uri "$Server/server/allow_apply" -Method POST -Body (@{allow=$true} | ConvertTo-Json) -ContentType "application/json" | Out-Null

# Simulate a burst of sequences using the Python driver (uses /sequences/*)
python scripts/sidecar_validate.py --server $Server | Out-String | Write-Host

# Show final status
Invoke-RestMethod -Uri "$Server/server/status" -Method GET | Format-List | Out-String | Write-Host
Invoke-RestMethod -Uri "$Server/apply/last" -Method GET | Format-List | Out-String | Write-Host
