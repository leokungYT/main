@echo off
chcp 65001 >nul
cd /d "%~dp0api"

echo ===================================================
echo   LGR API: Capture Auto
echo ===================================================
echo.

py -V >nul 2>&1
if %errorlevel% equ 0 (
    py capture_auto.py %*
) else (
    python capture_auto.py %*
)

echo.
pause
