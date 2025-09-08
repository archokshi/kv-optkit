# ====================================================================
# KV-OptKit Phase 1 Demo: Advisor
# ====================================================================
#
# This script demonstrates the Phase 1 advisor functionality. The advisor
# analyzes the workload and suggests optimization actions but does
# NOT execute them automatically.

# --- Step 1: Configuration ---
$env:KVOPT_PORT=9001
Write-Host "Step 1: Using port 9001 for the demo." -ForegroundColor Green


# --- Step 2: Start the Server ---
Write-Host "Step 2: Please start the server in a separate terminal by running:" -ForegroundColor Green
Write-Host "   PS> `$env:KVOPT_PORT=9001; python -m kvopt.server.main"
Read-Host "Press Enter to continue once the server is running..."


# --- Step 3: Set Initial State ---
Write-Host "`nStep 3: Submitting initial workload to the simulator..." -ForegroundColor Green
python examples/demo_cli.py reset
python examples/demo_cli.py submit --seq seq_1 --tokens 4000
python examples/demo_cli.py submit --seq seq_2 --tokens 3500

Write-Host "`nGetting initial telemetry..." -ForegroundColor Cyan
$initial_telemetry = Invoke-RestMethod -Method Get -Uri http://localhost:9001/telemetry
$initial_hbm = $initial_telemetry.hbm_utilization
Write-Host "Initial HBM Utilization: $initial_hbm"


# --- Step 4: Get Advisor Report ---
Write-Host "`nStep 4: Requesting an advisor report..." -ForegroundColor Green
$report = Invoke-RestMethod -Method Get -Uri http://localhost:9001/advisor/report

Write-Host "`nAdvisor Recommendations:" -ForegroundColor Cyan
$report | ConvertTo-Json -Depth 6
Write-Host "`nNote: These are only recommendations. The advisor in Phase 1 does not execute actions." -ForegroundColor Yellow


# --- Step 5: Verify No Changes ---
Write-Host "`nStep 5: Getting final telemetry to show that no actions were taken..." -ForegroundColor Green
$final_telemetry = Invoke-RestMethod -Method Get -Uri http://localhost:9001/telemetry
$final_hbm = $final_telemetry.hbm_utilization
Write-Host "Final HBM Utilization: $final_hbm"

if ($initial_hbm -eq $final_hbm) {
    Write-Host "As expected, HBM utilization has not changed." -ForegroundColor Yellow
}

# --- Step 6: Recommendation Summary (Plain Text Table) ---
Write-Host "`nStep 6: Recommendation Summary (plain text)" -ForegroundColor Green

function Get-Target($rec) {
  if ($rec.details -and $rec.details.target_sequence) { return $rec.details.target_sequence }
  return 'N/A'
}

function Get-Extra($rec) {
  if ($rec.details) {
    if ($rec.details.range) { return $rec.details.range }
    if ($rec.details.range_tokens) { return ($rec.details.range_tokens.ToString() + ' tokens') }
    if ($rec.details.suggested_factor) { return ('factor=' + $rec.details.suggested_factor) }
  }
  return ''
}

if ($report.recommendations -and $report.recommendations.Count -gt 0) {
  $header = ('{0,-10}  {1,-12}  {2,12}  {3,-8}  {4}' -f 'ACTION','TARGET','EST_SAV_GB','RISK','DETAIL')
  Write-Host $header -ForegroundColor Cyan
  Write-Host ('{0}' -f ('-' * $header.Length))

  foreach ($rec in $report.recommendations) {
    $action = $rec.action
    $target = Get-Target $rec
    $savings = '{0:N4}' -f [double]$rec.estimated_hbm_savings_gb
    $risk = $rec.risk
    $extra = Get-Extra $rec
    $detail = $rec.detail
    if ($extra -ne '') { $detail = "$detail [$extra]" }
    Write-Host ('{0,-10}  {1,-12}  {2,12}  {3,-8}  {4}' -f $action, $target, $savings, $risk, $detail)
  }
} else {
  Write-Host 'No recommendations available.' -ForegroundColor Yellow
}

Write-Host "`nDemo complete." -ForegroundColor Green
