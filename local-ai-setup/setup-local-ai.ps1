# Local AI Coding Stack Setup — REATAN Mini PC (Windows 11)
# Run from PowerShell as normal user (no admin required for Ollama)
# Usage: .\setup-local-ai.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "    WARN: $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "    FAIL: $msg" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Step 1 — Ollama
# ---------------------------------------------------------------------------
Write-Step "Step 1: Ollama"

$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    Write-OK "Ollama already installed: $(ollama --version)"
} else {
    Write-Host "    Downloading Ollama installer..."
    $ollamaInstaller = "$env:TEMP\OllamaSetup.exe"
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" `
        -OutFile $ollamaInstaller -UseBasicParsing
    Write-Host "    Running installer (no admin required)..."
    Start-Process -FilePath $ollamaInstaller -Wait
    # Refresh PATH so ollama is findable in this session
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        Write-OK "Ollama installed: $(ollama --version)"
    } else {
        Write-Fail "Ollama not found after install — open a new PowerShell window and re-run."
        exit 1
    }
}

# Pull model
Write-Host "    Pulling qwen2.5-coder:7b (this will take several minutes on first run)..."
ollama pull qwen2.5-coder:7b
Write-OK "Model qwen2.5-coder:7b ready"

# ---------------------------------------------------------------------------
# Step 2 — Open WebUI (Python path)
# ---------------------------------------------------------------------------
Write-Step "Step 2: Open WebUI"

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Warn "Python not found. Skipping Open WebUI — install Python 3.11+ from https://python.org then re-run."
} else {
    $pipList = python -m pip list 2>&1
    if ($pipList -match "open-webui") {
        Write-OK "open-webui already installed"
    } else {
        Write-Host "    Installing open-webui via pip..."
        python -m pip install open-webui --quiet
        Write-OK "open-webui installed"
    }
    Write-Host ""
    Write-Host "    To start Open WebUI: run  open-webui serve" -ForegroundColor Yellow
    Write-Host "    Then open: http://localhost:8080" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Step 3 — VS Code
# ---------------------------------------------------------------------------
Write-Step "Step 3: VS Code"

$codeCmd = Get-Command code -ErrorAction SilentlyContinue
if ($codeCmd) {
    Write-OK "VS Code already installed"
} else {
    # Try winget first (available on Win11)
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "    Installing VS Code via winget..."
        winget install --id Microsoft.VisualStudioCode --silent --accept-package-agreements --accept-source-agreements
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
        Write-OK "VS Code installed via winget"
    } else {
        Write-Warn "winget not available. Download VS Code from https://code.visualstudio.com and install manually."
    }
}

# ---------------------------------------------------------------------------
# Step 4 — Continue extension
# ---------------------------------------------------------------------------
Write-Step "Step 4: Continue VS Code extension"

$codeCmd = Get-Command code -ErrorAction SilentlyContinue
if ($codeCmd) {
    code --install-extension Continue.continue --force 2>&1 | Out-Null
    Write-OK "Continue extension installed"

    # Write Continue config
    $continueConfigDir = "$env:USERPROFILE\.continue"
    if (-not (Test-Path $continueConfigDir)) { New-Item -ItemType Directory -Path $continueConfigDir | Out-Null }
    $continueConfigPath = "$continueConfigDir\config.json"
    $continueConfig = @'
{
  "models": [
    {
      "title": "Qwen2.5 Coder 7B",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen2.5 Coder 7B",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b"
  }
}
'@
    Set-Content -Path $continueConfigPath -Value $continueConfig -Encoding UTF8
    Write-OK "Continue config written to $continueConfigPath"
} else {
    Write-Warn "VS Code not on PATH — install VS Code first, then run: code --install-extension Continue.continue"
}

# ---------------------------------------------------------------------------
# Step 5 — Git
# ---------------------------------------------------------------------------
Write-Step "Step 5: Git"

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    Write-OK "Git already installed: $(git --version)"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "    Installing Git via winget..."
        winget install --id Git.Git --silent --accept-package-agreements --accept-source-agreements
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + $env:PATH
        Write-OK "Git installed"
    } else {
        Write-Warn "winget not available. Download Git from https://git-scm.com and install manually."
    }
}

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    $currentName  = git config --global user.name  2>&1
    $currentEmail = git config --global user.email 2>&1
    if (-not $currentName)  { git config --global user.name  "Daniel Irving" }
    if (-not $currentEmail) { git config --global user.email "danirving1@gmail.com" }
    Write-OK "Git identity: $(git config --global user.name) <$(git config --global user.email)>"
}

# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Validation Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$checks = @(
    @{ Label = "ollama";             Cmd = { (Get-Command ollama -EA SilentlyContinue) -ne $null } }
    @{ Label = "qwen2.5-coder:7b";  Cmd = { (ollama list 2>&1) -match "qwen2.5-coder:7b" } }
    @{ Label = "VS Code (code)";    Cmd = { (Get-Command code   -EA SilentlyContinue) -ne $null } }
    @{ Label = "Continue config";   Cmd = { Test-Path "$env:USERPROFILE\.continue\config.json" } }
    @{ Label = "git";               Cmd = { (Get-Command git    -EA SilentlyContinue) -ne $null } }
)

foreach ($check in $checks) {
    try {
        if (& $check.Cmd) { Write-OK $check.Label }
        else               { Write-Fail $check.Label }
    } catch {
        Write-Fail "$($check.Label) — $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start Ollama service (runs automatically after install)"
Write-Host "  2. Run: open-webui serve  -> open http://localhost:8080"
Write-Host "  3. Open VS Code, click the Continue icon, ask it a coding question"
Write-Host "  4. Confirm Continue connects to Ollama (model: qwen2.5-coder:7b)"
Write-Host ""
