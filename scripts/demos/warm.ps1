param(
  [int]$Count = 20,
  [double]$Interval = 0.3,
  [string]$VLLMUrl = "http://localhost:8000",
  [string]$KVOptUrl = "http://localhost:9001"
)

$ErrorActionPreference = 'Stop'

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

function Wait-HttpOk($url, $timeoutSec = 120) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      # Use Invoke-RestMethod which handles JSON responses better
      $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5 -ErrorAction Stop
      if ($response) { return $true }
    } catch {
      # Continue trying on any error
    }
    Start-Sleep -Seconds 2
  }
  return $false
}

Assert-Command powershell

Write-Host "[warm] Waiting for vLLM at $VLLMUrl ..." -ForegroundColor Yellow
if (-not (Wait-HttpOk ("{0}/v1/models" -f $VLLMUrl) 180)) { throw "vLLM not reachable at $VLLMUrl" }

Write-Host "[warm] Waiting for KV-OptKit metrics at $KVOptUrl ..." -ForegroundColor Yellow
if (-not (Wait-HttpOk ("{0}/metrics" -f $KVOptUrl) 180)) { throw "KV-OptKit metrics not reachable at $KVOptUrl" }

Write-Host "[warm] Issuing warm requests ($Count @ ${Interval}s)" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File scripts/warm_vllm.ps1 -Count $Count -Interval $Interval
