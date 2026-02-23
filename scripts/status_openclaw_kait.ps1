# status_openclaw_kait.ps1 - Show OpenClaw bridge-layer status without assuming core ownership.
$ErrorActionPreference = "SilentlyContinue"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
if (-not (Test-Path "$RepoRoot\kaitd.py")) { $RepoRoot = (Get-Location).Path }

$pidFile = "$RepoRoot\scripts\.kait_openclaw_pids.json"
$kaitdPort = if ($env:KAITD_PORT -match "^\d+$") { [int]$env:KAITD_PORT } elseif ($env:KAITD_PORT -match "^\d+$") { [int]$env:KAITD_PORT } else { 8787 }

Write-Host "=== Kait x OpenClaw - Status ===" -ForegroundColor Cyan
Write-Host "PID file: $pidFile" -ForegroundColor DarkGray

if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile -Raw | ConvertFrom-Json
    Write-Host "Started: $($pids.started)" -ForegroundColor DarkGray
    Write-Host "Owner: $($pids.owner)" -ForegroundColor DarkGray
    Write-Host "WithCore: $($pids.with_core)" -ForegroundColor DarkGray

    $tailerPid = if ($pids.tailer) { [int]$pids.tailer } else { 0 }
    $tailer = if ($tailerPid) { Get-Process -Id $tailerPid -ErrorAction SilentlyContinue } else { $null }
    if ($tailer) {
        Write-Host "  [OK] openclaw_tailer - PID $tailerPid, CPU $([math]::Round($tailer.CPU, 1))s" -ForegroundColor Green
    } else {
        Write-Host "  [DEAD] openclaw_tailer - PID $tailerPid not running" -ForegroundColor Red
    }

    $ownedCore = @(
        @{ Name = "kaitd"; Pid = if ($pids.kaitd) { [int]$pids.kaitd } else { 0 }; Owned = [bool]$pids.owns_kaitd },
        @{ Name = "bridge_worker"; Pid = if ($pids.bridge) { [int]$pids.bridge } else { 0 }; Owned = [bool]$pids.owns_bridge }
    )
    foreach ($item in $ownedCore) {
        if (-not $item.Pid) { continue }
        $proc = Get-Process -Id $item.Pid -ErrorAction SilentlyContinue
        if ($proc) {
            $ownership = if ($item.Owned) { "owned" } else { "shared" }
            Write-Host "  [OK] $($item.Name) - PID $($item.Pid) ($ownership)" -ForegroundColor Green
        } else {
            Write-Host "  [DEAD] $($item.Name) - PID $($item.Pid) not running" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  No OpenClaw PID file found. Bridge-layer may not be running." -ForegroundColor Yellow
}

# Core kaitd HTTP health is reported as shared system status (not ownership).
Write-Host "`nkaitd HTTP check (shared core):" -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$kaitdPort/health" -TimeoutSec 3 -UseBasicParsing
    Write-Host "  [OK] kaitd responding ($($resp.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] kaitd not responding on :$kaitdPort" -ForegroundColor Red
}

$reportDir = Join-Path $env:USERPROFILE ".openclaw\workspace\kait_reports"
$reportCount = if (Test-Path $reportDir) { (Get-ChildItem "$reportDir\*.json" -ErrorAction SilentlyContinue).Count } else { 0 }
Write-Host "`nPending self-reports: $reportCount" -ForegroundColor $(if ($reportCount -gt 0) { "Yellow" } else { "DarkGray" })
