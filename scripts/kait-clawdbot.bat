@echo off
set "CMD=%KAIT_CLAWDBOT_CMD%"
if "%CMD%"=="" set "CMD=%KAIT_CLAWDBOT_CMD%"
if "%CMD%"=="" set "CMD=%CLAWDBOT_CMD%"
if "%CMD%"=="" set "CMD=clawdbot"
python -m kait.cli sync-context
%CMD% %*
