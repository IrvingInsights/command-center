$ErrorActionPreference = 'Stop'

Write-Host '=== PeakHinge Pipe Pivot Runner ==='

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
    throw 'Could not find FreeCADCmd.exe. Edit run_pipe_pivot.ps1 with your local FreeCAD path.'
}

Write-Host "Using FreeCAD command: $freecadCmd"

$modelsDir = Join-Path $repoRoot 'models'
$stepDir = Join-Path $repoRoot 'exports\step'
$stlDir = Join-Path $repoRoot 'exports\stl'

New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
New-Item -ItemType Directory -Force -Path $stepDir | Out-Null
New-Item -ItemType Directory -Force -Path $stlDir | Out-Null

& $freecadCmd (Join-Path $repoRoot 'scripts\build_pipe_pivot_v1.py')

Write-Host ''
Write-Host '=== Expected outputs ==='
Write-Host (Join-Path $modelsDir 'pipe_pivot_v1.FCStd')
Write-Host (Join-Path $stepDir 'pipe_pivot_v1.step')
Write-Host (Join-Path $stlDir 'pipe_pivot_v1.stl')

if (Test-Path (Join-Path $modelsDir 'pipe_pivot_v1.FCStd')) {
    Write-Host ''
    Write-Host 'Success: FCStd model was created.'
} else {
    Write-Host ''
    Write-Host 'The script ran, but the FCStd file was not found where expected.'
}
