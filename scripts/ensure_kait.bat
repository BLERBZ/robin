@echo off
REM Ensure Kait is running for the current project

setlocal
set PROJECT_DIR=%cd%
if "%KAIT_PULSE_DIR%"=="" (
    set "KAIT_PULSE_DIR=%~dp0..\kait\pulse"
    if not exist "%KAIT_PULSE_DIR%\app.py" (
        set "KAIT_PULSE_DIR=%~dp0..\..\vibeship-kait-pulse"
        if not exist "%KAIT_PULSE_DIR%\app.py" echo [warn] kait/pulse not found. Set KAIT_PULSE_DIR env var.
    )
)
python -m kait.cli ensure --sync-context --project "%PROJECT_DIR%"
