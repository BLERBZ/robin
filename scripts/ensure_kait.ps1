param(
    [string]$ProjectPath = (Get-Location).Path
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptRoot "..")
$inlinePulse = Join-Path $repoRoot.Path "kait\pulse"
$siblingPulse = Join-Path (Split-Path $repoRoot.Path -Parent) "vibeship-kait-pulse"

if (-not $env:KAIT_PULSE_DIR) {
    if (Test-Path (Join-Path $inlinePulse "app.py")) {
        $env:KAIT_PULSE_DIR = $inlinePulse
    } elseif (Test-Path (Join-Path $siblingPulse "app.py")) {
        $env:KAIT_PULSE_DIR = $siblingPulse
    } else {
        Write-Host "[warn] kait/pulse not found. Set KAIT_PULSE_DIR env var."
    }
}

python -m kait.cli ensure --sync-context --project "$ProjectPath"
