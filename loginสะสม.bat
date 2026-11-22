@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Auto Update Checker
cd /d "%~dp0"

echo =========================================
echo       Checking for updates...
echo =========================================

if not exist ".git" (
    echo [SKIP] Not a Git repo - skipping update check
    goto start_program
)

git fetch origin main >nul 2>&1

for /f "tokens=*" %%g in ('git rev-list HEAD...origin/main --count') do set "UPDATE_COUNT=%%g"
if "!UPDATE_COUNT!"=="" set "UPDATE_COUNT=0"

if !UPDATE_COUNT! GTR 0 (
    echo [!] New update found on Github!
    if exist _check_update.py (
        python _check_update.py
        if not errorlevel 1 (
            echo [UPDATE] Downloading latest files...
            git reset --hard origin/main
            git clean -f
            echo [DONE] Update complete!
        ) else (
            echo [SKIP] Update skipped by user
        )
    ) else (
        echo [UPDATE] auto-pulling latest ^(no _check_update.py^)
        git reset --hard origin/main
        git clean -f
        echo [DONE] Update complete!
    )
) else (
    echo [OK] Already up to date!
)

:start_program
echo.
echo =========================================
echo       Launching ExpressVPN...
echo =========================================

set "EVPN_EXE="
set "P1=C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P2=C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P3=C:\Program Files (x86)\ExpressVPN\ExpressVPN.exe"
set "P4=C:\Program Files\ExpressVPN\ExpressVPN.exe"
if exist "!P1!" set "EVPN_EXE=!P1!"
if "!EVPN_EXE!"=="" if exist "!P2!" set "EVPN_EXE=!P2!"
if "!EVPN_EXE!"=="" if exist "!P3!" set "EVPN_EXE=!P3!"
if "!EVPN_EXE!"=="" if exist "!P4!" set "EVPN_EXE=!P4!"

if "!EVPN_EXE!"=="" (
    echo [!] ExpressVPN not installed
    if exist "%~dp0INSTALL-EXPRESSVPN.bat" (
        echo     Run INSTALL-EXPRESSVPN.bat to install
        choice /C YN /T 10 /D N /M "Open INSTALL-EXPRESSVPN.bat now ^(Y=yes, N=skip, 10s auto-skip^)"
        if !errorlevel! equ 1 call "%~dp0INSTALL-EXPRESSVPN.bat"
    ) else (
        echo     INSTALL-EXPRESSVPN.bat not found in this folder
    )
    goto launch_swap
)

tasklist /FI "IMAGENAME eq ExpressVPN.exe" 2>nul | find /I "ExpressVPN.exe" >nul
if !errorlevel! equ 1 (
    echo [*] starting ExpressVPN
    start "" "!EVPN_EXE!"
    echo [*] waiting 8s for ExpressVPN to boot...
    timeout /t 8 /nobreak >nul
) else (
    echo [OK] ExpressVPN already running
)

:launch_swap
echo.
echo =========================================
echo       Launching swap_bot.py ^(VPN rotator^)
echo =========================================
set "SWAP_PY=%~dp0swap_bot\swap_bot.py"
if exist "!SWAP_PY!" (
    wmic process where "name='python.exe' or name='pythonw.exe'" get CommandLine 2>nul | find /I "swap_bot.py" >nul
    if !errorlevel! equ 1 (
        echo [*] starting swap_bot.py
        start "" /D "%~dp0swap_bot" pythonw "!SWAP_PY!"
    ) else (
        echo [OK] swap_bot already running
    )
) else (
    echo [SKIP] !SWAP_PY! not found
)

echo.
echo =========================================
echo       Starting program...
echo =========================================
echo.

python login.py
echo.
echo =========================================
echo       python login.py ended / error
echo =========================================
pause
endlocal
