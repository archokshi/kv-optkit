# ====================================================================
# KV-OptKit Phase 2 Demo: OFFLOAD
# ====================================================================
#
# This script demonstrates the impact of the OFFLOAD action.

# --- Step 1: Configuration ---
$env:KVOPT_PORT=9001
Write-Host "Step 1: Using port 9001 for the demo." -ForegroundColor Green


# --- Step 2: Start the Server ---
Write-Host "Step 2: Please start the server in a separate terminal by running:" -ForegroundColor Green
Write-Host "   PS> `$env:KVOPT_PORT=9001; python -m kvopt.server.main"
Read-Host "Press Enter to continue once the server is running..."


# --- Step 3: Set Initial State ---
Write-Host "`nStep 3: Submitting initial workload..." -ForegroundColor Green
python examples/demo_cli.py reset
python examples/demo_cli.py submit --seq seq_1 --tokens 4000
python examples/demo_cli.py submit --seq seq_2 --tokens 3500

Write-Host "`nGetting initial telemetry..." -ForegroundColor Cyan
$initial_telemetry = Invoke-RestMethod -Method Get -Uri http://localhost:9001/telemetry
$initial_hbm = $initial_telemetry.hbm_utilization
Write-Host "Initial HBM Utilization: $initial_hbm"


# --- Step 4: Run Autopilot with OFFLOAD ---
Write-Host "`nStep 4: Requesting an OFFLOAD-only plan..." -ForegroundColor Green
$body = @{
  target_hbm_util = 0.001
  allowed_actions = @("OFFLOAD")
} | ConvertTo-Json

$plan = Invoke-RestMethod -Method Post -Uri http://localhost:9001/autopilot/plan -ContentType 'application/json' -Body $body

Write-Host "`nAutopilot Plan Details:" -ForegroundColor Cyan
$plan | ConvertTo-Json -Depth 6


# --- Step 5: Show Final State ---
Write-Host "`nStep 5: Getting final telemetry..." -ForegroundColor Green
Start-Sleep -Seconds 1
$final_telemetry = Invoke-RestMethod -Method Get -Uri http://localhost:9001/telemetry
$final_hbm = $final_telemetry.hbm_utilization
Write-Host "Final HBM Utilization: $final_hbm"

$reduction = $initial_hbm - $final_hbm
$reduction_percent = ($reduction / $initial_hbm) * 100
Write-Host "HBM Utilization was reduced by $($reduction.ToString("F4")) (a $($reduction_percent.ToString("F2"))% improvement)." -ForegroundColor Yellow


Write-Host "`nDemo complete." -ForegroundColor Green
