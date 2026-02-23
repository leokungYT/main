@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo   Ranger+Gear Multi-Window Launcher
echo ======================================================

:: Find all connected devices
echo [INFO] Searching for devices...
for /f "tokens=1,2" %%a in ('adb devices ^| findstr /v "List"') do (
    if "%%b"=="device" (
        set "device=%%a"
        echo [START] Launching for %%a in new window...
        start "Bot-%%a" cmd /k "python ranger-gear.py --device %%a --cli"
        timeout /t 5 /nobreak >nul
    )
)

echo [DONE] All windows launched.
pause
