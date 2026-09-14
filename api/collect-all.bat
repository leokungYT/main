@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   LGR API: Collect All (creds.json)
echo ===================================================
echo.

py -V >nul 2>&1
if %errorlevel% equ 0 (
    py collect_all.py %*
) else (
    python collect_all.py %*
)

echo.
pause
