@echo off
REM Kait Intelligence - Windows Startup Script
REM Starts: Mind (8080), kaitd (8787), bridge_worker, pulse (8765), watchdog

setlocal
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
if "%KAIT_PULSE_DIR%"=="" (
    set "KAIT_PULSE_DIR=%~dp0kait\pulse"
    if not exist "%KAIT_PULSE_DIR%\app.py" (
        set "KAIT_PULSE_DIR=%~dp0..\vibeship-kait-pulse"
        if not exist "%KAIT_PULSE_DIR%\app.py" echo [warn] kait/pulse not found. Set KAIT_PULSE_DIR env var.
    )
)
cd /d %~dp0

REM R3 chip profile defaults (overridable via environment).
if "%KAIT_CHIP_REQUIRE_LEARNING_SCHEMA%"=="" if "%KAIT_CHIP_REQUIRE_LEARNING_SCHEMA%"=="" set KAIT_CHIP_REQUIRE_LEARNING_SCHEMA=1
if "%KAIT_CHIP_OBSERVER_ONLY%"=="" if "%KAIT_CHIP_OBSERVER_ONLY%"=="" set KAIT_CHIP_OBSERVER_ONLY=1
if "%KAIT_CHIP_MIN_LEARNING_EVIDENCE%"=="" if "%KAIT_CHIP_MIN_LEARNING_EVIDENCE%"=="" set KAIT_CHIP_MIN_LEARNING_EVIDENCE=2
if "%KAIT_CHIP_MIN_CONFIDENCE%"=="" if "%KAIT_CHIP_MIN_CONFIDENCE%"=="" set KAIT_CHIP_MIN_CONFIDENCE=0.65
if "%KAIT_CHIP_MIN_SCORE%"=="" if "%KAIT_CHIP_MIN_SCORE%"=="" set KAIT_CHIP_MIN_SCORE=0.25
if "%KAIT_CHIP_MERGE_MIN_CONFIDENCE%"=="" if "%KAIT_CHIP_MERGE_MIN_CONFIDENCE%"=="" set KAIT_CHIP_MERGE_MIN_CONFIDENCE=0.65
if "%KAIT_CHIP_MERGE_MIN_QUALITY%"=="" if "%KAIT_CHIP_MERGE_MIN_QUALITY%"=="" set KAIT_CHIP_MERGE_MIN_QUALITY=0.62

REM Phase 1 advisory/learning flags (overridable via environment).
if "%KAIT_ADVISORY_AGREEMENT_GATE%"=="" set KAIT_ADVISORY_AGREEMENT_GATE=1
if "%KAIT_ADVISORY_AGREEMENT_MIN_SOURCES%"=="" set KAIT_ADVISORY_AGREEMENT_MIN_SOURCES=2
if "%KAIT_PIPELINE_IMPORTANCE_SAMPLING%"=="" if "%KAIT_PIPELINE_IMPORTANCE_SAMPLING%"=="" set KAIT_PIPELINE_IMPORTANCE_SAMPLING=1
if "%KAIT_PIPELINE_LOW_KEEP_RATE%"=="" if "%KAIT_PIPELINE_LOW_KEEP_RATE%"=="" set KAIT_PIPELINE_LOW_KEEP_RATE=0.25
if "%KAIT_MACROS_ENABLED%"=="" if "%KAIT_MACROS_ENABLED%"=="" set KAIT_MACROS_ENABLED=1
if "%KAIT_MACRO_MIN_COUNT%"=="" if "%KAIT_MACRO_MIN_COUNT%"=="" set KAIT_MACRO_MIN_COUNT=3

REM Phase 2 memory flags (overridable via environment).
if "%KAIT_MEMORY_PATCHIFIED%"=="" if "%KAIT_MEMORY_PATCHIFIED%"=="" set KAIT_MEMORY_PATCHIFIED=1
if "%KAIT_MEMORY_PATCH_MAX_CHARS%"=="" if "%KAIT_MEMORY_PATCH_MAX_CHARS%"=="" set KAIT_MEMORY_PATCH_MAX_CHARS=600
if "%KAIT_MEMORY_PATCH_MIN_CHARS%"=="" if "%KAIT_MEMORY_PATCH_MIN_CHARS%"=="" set KAIT_MEMORY_PATCH_MIN_CHARS=120
if "%KAIT_MEMORY_DELTAS%"=="" if "%KAIT_MEMORY_DELTAS%"=="" set KAIT_MEMORY_DELTAS=1
if "%KAIT_MEMORY_DELTA_MIN_SIM%"=="" if "%KAIT_MEMORY_DELTA_MIN_SIM%"=="" set KAIT_MEMORY_DELTA_MIN_SIM=0.86

REM Phase 3 advisory intelligence flags (overridable via environment).
if "%KAIT_OUTCOME_PREDICTOR%"=="" if "%KAIT_OUTCOME_PREDICTOR%"=="" set KAIT_OUTCOME_PREDICTOR=1

REM Advisory: cheap fallback hint when time budget is low (improves real-time delivery).
if "%KAIT_ADVISORY_LIVE_QUICK_FALLBACK%"=="" set KAIT_ADVISORY_LIVE_QUICK_FALLBACK=1
if "%KAIT_ADVISORY_LIVE_QUICK_MIN_REMAINING_MS%"=="" set KAIT_ADVISORY_LIVE_QUICK_MIN_REMAINING_MS=900

REM Advisory: action-first formatting (put Next check command on first line)
if "%KAIT_ADVISORY_ACTION_FIRST%"=="" set KAIT_ADVISORY_ACTION_FIRST=1

if "%KAIT_NO_MIND%"=="1" goto start_kait
if "%KAIT_NO_MIND%"=="1" goto start_kait
set MIND_PORT=%KAIT_MIND_PORT%
if "%MIND_PORT%"=="" set MIND_PORT=%KAIT_MIND_PORT%
if "%MIND_PORT%"=="" set MIND_PORT=8080
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_mind.ps1" -MindPort %MIND_PORT%

:start_kait
echo.
echo =============================================
echo   KAIT - Self-Evolving Intelligence Layer
echo =============================================
echo.

set "KAIT_ARGS="
if /I "%KAIT_LITE%"=="1" set "KAIT_ARGS=--lite"
if /I "%KAIT_LITE%"=="1" if "%KAIT_ARGS%"=="" set "KAIT_ARGS=--lite"
if /I "%KAIT_NO_PULSE%"=="1" set "KAIT_ARGS=%KAIT_ARGS% --no-pulse"
if /I "%KAIT_NO_PULSE%"=="1" if not defined KAIT_NO_PULSE set "KAIT_ARGS=%KAIT_ARGS% --no-pulse"
if /I "%KAIT_NO_WATCHDOG%"=="1" set "KAIT_ARGS=%KAIT_ARGS% --no-watchdog"
if /I "%KAIT_NO_WATCHDOG%"=="1" if not defined KAIT_NO_WATCHDOG set "KAIT_ARGS=%KAIT_ARGS% --no-watchdog"

python -m kait.cli up %KAIT_ARGS%
python -m kait.cli services

echo.
echo Press any key to exit (services will continue running)...
pause > nul
