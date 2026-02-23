@echo off
set "CMD=%KAIT_CURSOR_CMD%"
if "%CMD%"=="" set "CMD=%KAIT_CURSOR_CMD%"
if "%CMD%"=="" set "CMD=%CURSOR_CMD%"
if "%CMD%"=="" set "CMD=cursor"
python -m kait.cli sync-context
%CMD% %*
