@echo off
chcp 65001 >nul
cd /d "%~dp0api"

echo ===================================================
echo   LGR API: Test Login (creds.json)
echo ===================================================
echo.

py -V >nul 2>&1
if %errorlevel% equ 0 (
    py test_login.py %*
) else (
    python test_login.py %*
)

echo.
pause
