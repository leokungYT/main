@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo   Ranger+Gear Multi-Process Launcher (With GUI)
echo ======================================================

:: Determine ADB Path
set "ADB_EXE=adb.exe"
if exist "adb\adb.exe" (
    set "ADB_EXE=adb\adb.exe"
    echo [INFO] Using local ADB: !ADB_EXE!
) else (
    echo [INFO] Local ADB not found, trying system PATH...
)

:: 1. Cleanup old shared stats
if exist "shared_stats.json" del "shared_stats.json"

:: 2. Launch Main GUI in background (it will now aggregate stats from other processes)
echo [GUI] Launching Main UI...
start "Ranger-GUI" python ranger-gear.py --no-reset-adb --no-start
timeout /t 5 /nobreak >nul

:: 3. Find and launch minimized CMDs for each device
echo [INFO] Searching for devices to start WORKERS...
for /f "tokens=1,2" %%a in ('!ADB_EXE! devices ^| findstr /v "List"') do (
    if "%%b"=="device" (
        echo [WORKER] Starting background process for %%a...
        :: Using --minimized flag we just added, plus --cli
        start "Bot-%%a" python ranger-gear.py --device %%a --cli --minimized --no-reset-adb
        timeout /t 2 /nobreak >nul
    )
)

echo [DONE] GUI is open, all workers are running minimized.
exit
