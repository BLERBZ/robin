@echo off
set "CMD=%KAIT_CLAUDE_CMD%"
if "%CMD%"=="" set "CMD=%KAIT_CLAUDE_CMD%"
if "%CMD%"=="" set "CMD=%CLAUDE_CMD%"
if "%CMD%"=="" set "CMD=claude"
python -m kait.cli sync-context
%CMD% %*
