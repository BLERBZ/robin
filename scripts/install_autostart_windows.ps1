param(
    [string]$TaskName = "Kait Up",
    [string]$ProjectPath = "",
    [string]$PythonPath = "",
    [string]$PulsePath = ""
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = $repoRoot.Path
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        throw "python not found on PATH. Provide -PythonPath."
    }
    $PythonPath = $py.Source
}

if ([string]::IsNullOrWhiteSpace($PulsePath)) {
    $inlinePulse = Join-Path $repoRoot.Path "kait\pulse"
    $siblingPulse = Join-Path (Split-Path $repoRoot.Path -Parent) "vibeship-kait-pulse"
    if (Test-Path (Join-Path $inlinePulse "app.py")) {
        $PulsePath = $inlinePulse
    } elseif (Test-Path (Join-Path $siblingPulse "app.py")) {
        $PulsePath = $siblingPulse
    } else {
        Write-Host "[warn] kait/pulse not found. Set KAIT_PULSE_DIR env var."
        $PulsePath = $null
    }
}

$taskCmd = 'cmd /c "set ""KAIT_PULSE_DIR={0}"" && ""{1}"" -m kait.cli up --sync-context --project ""{2}"""' -f $PulsePath, $PythonPath, $ProjectPath

Write-Host "Creating scheduled task: $TaskName"
Write-Host "Command: $taskCmd"

schtasks /Create /TN "$TaskName" /TR "$taskCmd" /SC ONLOGON /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create scheduled task. Try running PowerShell as Administrator."
}

Write-Host "Done. Task will run at user logon."
