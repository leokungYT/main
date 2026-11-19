@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   RUN FROM CREDS - headless login, no MuMu, no XML, no key
echo ============================================================
echo.

if not exist "creds.json" (
    echo [!] creds.json ไม่มี - รัน COLLECT-CREDS.bat ก่อน
    pause
    endlocal
    exit /b 1
)

python -X utf8 run_from_creds.py %1 %2 %3 %4 %5 %6 %7 %8 %9

pause
endlocal
