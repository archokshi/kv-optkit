param(
  [string]$Compose="docker/demos/gpu/docker-compose.gpu.baseline.yaml",
  [string]$Scenario="baseline_gpu",
  [switch]$StayUp
)

$ErrorActionPreference = "Stop"

function Test-GPUReady {
  try {
    docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi | Out-Null
    return $true
  } catch {
    return $false
  }
}

Write-Host "[KVOPT] Phase 7 GPU scenario: $Scenario" -ForegroundColor Cyan

if (-not (Test-GPUReady)) {
  Write-Warning "GPU is not available to Docker. Skipping run. Validate NVIDIA Windows driver, WSL2, and Docker Desktop GPU integration (Settings → Resources → GPU)."
  exit 2
}

Write-Host "[KVOPT] Bringing up compose: $Compose" -ForegroundColor Cyan
& docker compose -f $Compose up -d

# Wait a bit for services
Start-Sleep -Seconds 10

# Warm step: vLLM /v1/models
$warmOk = $false
for ($i=0; $i -lt 12; $i++) {
  try {
    $resp = Invoke-RestMethod -Uri http://localhost:8000/v1/models -TimeoutSec 3
    if ($resp) { $warmOk = $true; break }
  } catch { Start-Sleep -Seconds 5 }
}
if (-not $warmOk) {
  Write-Error "Warm step failed: /v1/models not responding."
  if (-not $StayUp) { & docker compose -f $Compose down -v }
  exit 1
}
Write-Host "[KVOPT] Warm step passed (vLLM /v1/models)." -ForegroundColor Green

# Short generate: call OpenAI completions/chat if available (best-effort)
try {
  $body = @{ model = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"; prompt = "Hello"; max_tokens = 8 } | ConvertTo-Json
  $gen = Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/completions -ContentType 'application/json' -Body $body -TimeoutSec 5
  if ($gen) { Write-Host "[KVOPT] Short generation returned tokens (best-effort)." -ForegroundColor Green }
} catch { Write-Warning "Short generation check skipped/failed (non-fatal)." }

# Short traffic to KV-OptKit (best-effort)
try {
  1..20 | ForEach-Object {
    Invoke-RestMethod -Uri http://localhost:9001/healthz -TimeoutSec 2 | Out-Null
  }
  Write-Host "[KVOPT] Short traffic sent to KV-OptKit." -ForegroundColor Green
} catch { Write-Warning "KV-OptKit traffic check skipped/failed (non-fatal)." }

if (-not $StayUp) {
  & docker compose -f $Compose down -v
}
