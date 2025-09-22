param(
  [Parameter(Mandatory=$true)][string]$A,
  [Parameter(Mandatory=$true)][string]$B,
  [int]$WarmCount = 20,
  [double]$WarmInterval = 0.3,
  [int]$AutoCount = 20,
  [double]$AutoInterval = 0.5,
  [int]$HoldSeconds = 0,
  [switch]$StayUp,
  [switch]$NoBrowser
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
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
      if ($resp.StatusCode -eq 200) { return $true }
    } catch { Start-Sleep -Seconds 1 }
  }
  return $false
}

$map = @{
  'baseline.cpu'               = 'docker/demos/cpu/docker-compose.cpu.baseline.yaml'
  'advisor_with_lmcache.cpu'   = 'docker/demos/cpu/docker-compose.cpu.advisor.lmcache.yaml'
  'advisor_without_lmcache.cpu'= 'docker/demos/cpu/docker-compose.cpu.advisor.nocache.yaml'
  'lmcache_only.cpu'           = 'docker/demos/cpu/docker-compose.cpu.lmcache.only.yaml'
  'autopilot_with_lmcache.cpu' = 'docker/demos/cpu/docker-compose.cpu.autopilot.lmcache.yaml'
}

Assert-Command docker
Assert-Command python

if (-not $map.ContainsKey($A)) { throw "Unknown scenario A: $A" }
if (-not $map.ContainsKey($B)) { throw "Unknown scenario B: $B" }

function Run-Scenario($name, $label) {
  $compose = $map[$name]
  Write-Host "[A/B] Starting $name using $compose" -ForegroundColor Cyan
  docker compose -f $compose up --build -d | Out-Null

  if (-not (Wait-HttpOk "http://localhost:8000/v1/models" 180)) { throw "vLLM endpoint not reachable :8000" }
  if (-not (Wait-HttpOk "http://localhost:9001/metrics" 120)) { throw "KV-OptKit metrics not reachable :9001" }

  Write-Host "[A/B] Warming ($WarmCount @ ${WarmInterval}s)" -ForegroundColor Yellow
  powershell -ExecutionPolicy Bypass -File scripts/demos/warm.ps1 -Count $WarmCount -Interval $WarmInterval | Out-Null

  Write-Host "[A/B] Generating traffic ($AutoCount @ ${AutoInterval}s) label=$label" -ForegroundColor Yellow
  python scripts/generate_autopilot_traffic.py --count $AutoCount --interval $AutoInterval --label "phase=$label"

  if ($HoldSeconds -gt 0) {
    Write-Host "[A/B] Holding $name up for $HoldSeconds seconds for Grafana observation..." -ForegroundColor Green
    Start-Sleep -Seconds $HoldSeconds
  }

  if (-not $StayUp) {
    Start-Sleep -Seconds 3
    docker compose -f $compose down | Out-Null
  } else {
    Write-Host "[A/B] StayUp specified: leaving $name running. Remember to stop it later with:`n  docker compose -f $compose down" -ForegroundColor Yellow
  }
}

Run-Scenario -name $A -label ($A.Replace('.','_'))
Run-Scenario -name $B -label ($B.Replace('.','_'))

if (-not $NoBrowser) { Start-Process "http://localhost:3001/d/kvopt-ab-cpu/kv-optkit-phase-6-a-b-cpu" }

Write-Host "[A/B] Completed. Compare labels for $A vs $B" -ForegroundColor Green
