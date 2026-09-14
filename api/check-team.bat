@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   LGR API: Check Team (creds.json)
echo ===================================================
echo.

py -V >nul 2>&1
if %errorlevel% equ 0 (
    py check_team.py %*
) else (
    python check_team.py %*
)

echo.
pause
