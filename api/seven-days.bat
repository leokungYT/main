@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   LGR API: Seven Days Mission (creds.json)
echo ===================================================
echo.

py -V >nul 2>&1
if %errorlevel% equ 0 (
    py seven_days.py %*
) else (
    python seven_days.py %*
)

echo.
pause
