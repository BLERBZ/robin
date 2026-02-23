@echo off
set "CMD=%KAIT_CODEX_CMD%"
if "%CMD%"=="" set "CMD=%KAIT_CODEX_CMD%"
if "%CMD%"=="" set "CMD=%CODEX_CMD%"
if "%CMD%"=="" set "CMD=codex"
if "%KAIT_SYNC_TARGETS%"=="" if "%KAIT_SYNC_TARGETS%"=="" set "KAIT_SYNC_TARGETS=codex"
python -m kait.cli sync-context
%CMD% %*
