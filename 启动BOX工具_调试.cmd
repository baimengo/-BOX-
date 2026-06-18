@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_python.ps1" -Script "%~dp0main.py"
pause
