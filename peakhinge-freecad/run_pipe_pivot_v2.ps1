$ErrorActionPreference = 'Stop'

Write-Host '=== PeakHinge Pipe Pivot Runner v2 ==='

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$candidatePaths = @(
    'C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe',
    'C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe',
    'C:\Program Files\FreeCAD\bin\FreeCADCmd.exe'
)

$freecadCmd = $null
foreach ($path in $candidatePaths) {
    if (Test-Path $path) {
        $freecadCmd = $path
        break
    }
}

if (-not $freecadCmd) {
    $cmd = Get-Command FreeCADCmd.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $freecadCmd = $cmd.Source
    }
}

if (-not $freecadCmd) {
    throw 'Could not find FreeCADCmd.exe. Edit run_pipe_pivot_v2.ps1 with your local FreeCAD path.'
}

Write-Host "Using FreeCAD command: $freecadCmd"

$modelsDir = Join-Path $repoRoot 'models'
$stepDir = Join-Path $repoRoot 'exports\step'
$stlDir = Join-Path $repoRoot 'exports\stl'

New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $stepDir | Out-Null
New-Item -ItemType Directory -Force -Path $stlDir | Out-Null

$scriptPath = Join-Path $repoRoot 'scripts\build_pipe_pivot_v1.py'

if (-not (Test-Path $scriptPath)) {
    throw "Script not found: $scriptPath"
}

# FreeCAD 1.0.x may not reliably execute a .py path directly from FreeCADCmd.
# Force execution through -c and explicitly define __file__.
$escapedScriptPath = $scriptPath.Replace('\', '\\')
$pythonCommand = "import os; p=r'$escapedScriptPath'; os.chdir(os.path.dirname(p)); g={'__name__':'__main__','__file__':p}; exec(open(p,'r',encoding='utf-8').read(), g)"

Write-Host 'Running script through FreeCADCmd -c ...'
& $freecadCmd -c $pythonCommand
$exitCode = $LASTEXITCODE

Write-Host ''
Write-Host "FreeCAD exit code: $exitCode"
Write-Host ''
Write-Host '=== Expected outputs ==='
Write-Host (Join-Path $modelsDir 'pipe_pivot_v1.FCStd')
Write-Host (Join-Path $stepDir 'pipe_pivot_v1.step')
Write-Host (Join-Path $stlDir 'pipe_pivot_v1.stl')

$fcstdPath = Join-Path $modelsDir 'pipe_pivot_v1.FCStd'
$stepPath = Join-Path $stepDir 'pipe_pivot_v1.step'
$stlPath = Join-Path $stlDir 'pipe_pivot_v1.stl'

if ((Test-Path $fcstdPath) -and (Test-Path $stepPath) -and (Test-Path $stlPath)) {
    Write-Host ''
    Write-Host 'Success: FCStd, STEP, and STL files were created.'
} else {
    Write-Host ''
    Write-Host 'One or more expected output files were not created.'
    Write-Host "FCStd exists: $(Test-Path $fcstdPath)"
    Write-Host "STEP exists:  $(Test-Path $stepPath)"
    Write-Host "STL exists:   $(Test-Path $stlPath)"
}
