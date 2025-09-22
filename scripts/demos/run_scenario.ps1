param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("baseline", "advisor_without_lmcache", "advisor_with_lmcache", "lmcache_only", "autopilot_with_lmcache")]
  [string]$Scenario,
  
  [int]$WarmCount = 20,
  [double]$WarmInterval = 0.3,
  [int]$TrafficCount = 10,
  [double]$TrafficInterval = 0.5,
  [int]$TrafficLoops = 60,
  [int]$LoopSleep = 10,
  [switch]$StayUp
)

$ErrorActionPreference = 'Stop'

# Map scenario to compose file and phase label
$scenarioMap = @{
  "baseline" = @{
    ComposeFile = "docker/demos/cpu/docker-compose.cpu.baseline.yaml"
    PhaseLabel = "baseline"
  }
  "advisor_without_lmcache" = @{
    ComposeFile = "docker/demos/cpu/docker-compose.cpu.advisor.nocache.yaml"
    PhaseLabel = "advisor_no_cache"
  }
  "advisor_with_lmcache" = @{
    ComposeFile = "docker/demos/cpu/docker-compose.cpu.advisor.lmcache.yaml"
    PhaseLabel = "advisor_with_cache"
  }
  "lmcache_only" = @{
    ComposeFile = "docker/demos/cpu/docker-compose.cpu.lmcache.only.yaml"
    PhaseLabel = "lmcache_only"
  }
  "autopilot_with_lmcache" = @{
    ComposeFile = "docker/demos/cpu/docker-compose.cpu.autopilot.lmcache.yaml"
    PhaseLabel = "autopilot_with_cache"
  }
}

$config = $scenarioMap[$Scenario]
$composeFile = $config.ComposeFile
$phaseLabel = $config.PhaseLabel

Write-Host "[$Scenario] Starting scenario..." -ForegroundColor Cyan

# Step 1: Clean up any existing containers to free ports
Write-Host "[$Scenario] Cleaning up existing containers..." -ForegroundColor Yellow
foreach ($file in $scenarioMap.Values.ComposeFile) {
  try {
    docker compose -f $file down 2>$null
  } catch {
    # Ignore errors for non-running stacks
  }
}

# Step 2: Set Redis port if needed (for LMCache scenarios)
if ($Scenario -match "lmcache|advisor_with_lmcache|autopilot_with_lmcache") {
  $env:REDIS_PORT = "6379"
}

# Step 3: Start the scenario
Write-Host "[$Scenario] Starting containers..." -ForegroundColor Green
docker compose -f $composeFile up --build -d

# Step 4: Wait for services and warm
Write-Host "[$Scenario] Warming system..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File scripts/demos/warm.ps1 -Count $WarmCount -Interval $WarmInterval

# Step 5: Generate sustained traffic
Write-Host "[$Scenario] Generating traffic ($TrafficLoops loops of $TrafficCount requests)..." -ForegroundColor Green
for ($i=0; $i -lt $TrafficLoops; $i++) {
  Write-Host "[$Scenario] Loop $($i+1)/$TrafficLoops" -ForegroundColor DarkGray
  python scripts/generate_autopilot_traffic.py --count $TrafficCount --interval $TrafficInterval --label "phase=$phaseLabel"
  Start-Sleep -Seconds $LoopSleep
}

# Step 6: Cleanup (unless StayUp)
if (-not $StayUp) {
  Write-Host "[$Scenario] Cleaning up..." -ForegroundColor Yellow
  docker compose -f $composeFile down
  Write-Host "[$Scenario] Complete." -ForegroundColor Green
} else {
  Write-Host "[$Scenario] Scenario running. Stop with: docker compose -f $composeFile down" -ForegroundColor Cyan
}
