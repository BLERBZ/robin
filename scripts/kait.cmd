@echo off
setlocal
cd /d "%~dp0.."
python -m kait.cli %*
exit /b %errorlevel%
