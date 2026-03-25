$ErrorActionPreference = 'Stop'

Write-Host '=== PeakHinge Step 1 App Verification ==='

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonCmd = $null
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) {
    $pythonCmd = @($py.Source, '-3')
} else {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        $pythonCmd = @($python.Source)
    }
}

if (-not $pythonCmd) {
    throw 'Could not find Python 3. Install Python or adjust verify_step1_app.ps1.'
}

function Run-PythonScript {
    param(
        [string]$ScriptPath,
        [string[]]$Args = @(),
        [string]$Label
    )

    Write-Host ''
    Write-Host "--- $Label ---"
    $cmd = $pythonCmd + @($ScriptPath) + $Args
    Write-Host ('$ ' + ($cmd -join ' '))
    & $cmd[0] $cmd[1..($cmd.Length-1)]
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$readinessScript = Join-Path $repoRoot 'scripts\readiness_check.py'
$runnerScript = Join-Path $repoRoot 'scripts\step1_chat_runner.py'

if (-not (Test-Path $readinessScript)) {
    throw "Missing readiness script: $readinessScript"
}
if (-not (Test-Path $runnerScript)) {
    throw "Missing runner script: $runnerScript"
}

Run-PythonScript -ScriptPath $readinessScript -Label 'Readiness check'
Run-PythonScript -ScriptPath $runnerScript -Args @('--request', 'set bore diameter to 65 mm', '--strict-freecad') -Label 'Strict FreeCAD chat-runner test'

Write-Host ''
Write-Host 'If the runner succeeded, check these locations:'
Write-Host (Join-Path $repoRoot 'runtime')
Write-Host (Join-Path $repoRoot 'models\pipe_pivot_v1.FCStd')
Write-Host (Join-Path $repoRoot 'exports\step\pipe_pivot_v1.step')
Write-Host (Join-Path $repoRoot 'exports\stl\pipe_pivot_v1.stl')

Write-Host ''
Write-Host 'Step 1 verification script completed successfully.'
