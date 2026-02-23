@echo off
set "CMD=%KAIT_WINDSURF_CMD%"
if "%CMD%"=="" set "CMD=%KAIT_WINDSURF_CMD%"
if "%CMD%"=="" set "CMD=%WINDSURF_CMD%"
if "%CMD%"=="" set "CMD=windsurf"
python -m kait.cli sync-context
%CMD% %*
