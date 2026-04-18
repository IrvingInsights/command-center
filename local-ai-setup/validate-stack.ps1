# Validate local AI stack is fully operational
# Run after setup-local-ai.ps1 to confirm everything works end-to-end
# Usage: .\validate-stack.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

function Write-OK   { param([string]$msg) Write-Host "  [PASS] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Info { param([string]$msg) Write-Host "         $msg" -ForegroundColor Gray }

$allPassed = $true

Write-Host "`nLocal AI Stack — Validation" -ForegroundColor Cyan
Write-Host "===========================`n"

# 1. Ollama binary
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) { Write-OK "Ollama binary found: $(ollama --version)" }
else         { Write-Fail "Ollama not found — run setup-local-ai.ps1"; $allPassed = $false }

# 2. Model present
$modelList = ollama list 2>&1
if ($modelList -match "qwen2.5-coder") {
    Write-OK "qwen2.5-coder:7b model is pulled"
} else {
    Write-Fail "qwen2.5-coder:7b not found — run: ollama pull qwen2.5-coder:7b"
    $allPassed = $false
}

# 3. Ollama API responding
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method GET -TimeoutSec 5
    Write-OK "Ollama API is running at http://localhost:11434"
} catch {
    Write-Fail "Ollama API not reachable — start Ollama from the system tray or run: ollama serve"
    Write-Info "Ollama usually starts automatically after install."
    $allPassed = $false
}

# 4. Quick model inference test
try {
    $body = '{"model":"qwen2.5-coder:7b","prompt":"Reply with only the word: READY","stream":false}'
    $result = Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
        -Method POST -Body $body -ContentType "application/json" -TimeoutSec 60
    if ($result.response -match "READY") {
        Write-OK "Model inference works — got expected response"
    } else {
        Write-OK "Model inference works — response: $($result.response.Trim())"
    }
} catch {
    Write-Fail "Model inference failed: $_"
    $allPassed = $false
}

# 5. VS Code
$code = Get-Command code -ErrorAction SilentlyContinue
if ($code) { Write-OK "VS Code installed" }
else       { Write-Fail "VS Code not on PATH"; $allPassed = $false }

# 6. Continue config
$configPath = "$env:USERPROFILE\.continue\config.json"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $hasOllama = $config.models | Where-Object { $_.provider -eq "ollama" }
    if ($hasOllama) { Write-OK "Continue config exists and points to Ollama" }
    else            { Write-Fail "Continue config missing Ollama entry"; $allPassed = $false }
} else {
    Write-Fail "Continue config not found at $configPath"
    $allPassed = $false
}

# 7. Git
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    $name  = git config --global user.name  2>&1
    $email = git config --global user.email 2>&1
    Write-OK "Git installed: $(git --version)"
    Write-Info "Identity: $name <$email>"
} else {
    Write-Fail "Git not installed"
    $allPassed = $false
}

# 8. Open WebUI (optional — may not be running)
try {
    $webui = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 3 -UseBasicParsing
    Write-OK "Open WebUI is running at http://localhost:8080"
} catch {
    Write-Host "  [INFO] Open WebUI not running — start with: open-webui serve" -ForegroundColor Yellow
}

Write-Host ""
if ($allPassed) {
    Write-Host "All checks passed. Stack is ready." -ForegroundColor Green
} else {
    Write-Host "Some checks failed — see details above." -ForegroundColor Red
}
Write-Host ""
