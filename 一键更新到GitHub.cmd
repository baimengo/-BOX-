@echo off
setlocal
title GitHub Repository Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\update_github.ps1" %*
set "update_exit_code=%errorlevel%"
echo.
if not "%update_exit_code%"=="0" echo Update stopped. See the error message and log path above.
pause
exit /b %update_exit_code%
