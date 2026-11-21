@echo off
chcp 65001 >nul
title Auto Update Checker
cd /d "%~dp0"

echo =========================================
echo       Checking for updates...
echo =========================================

:: Check if this is a Git repository
if not exist ".git" (
    echo [SKIP] Not a Git repo - skipping update check
    goto start_program
)

:: Fetch latest from Github
git fetch origin main >nul 2>&1

:: Count how many commits behind
for /f "tokens=*" %%g in ('git rev-list HEAD...origin/main --count') do (set UPDATE_COUNT=%%g)
if "%UPDATE_COUNT%"=="" set UPDATE_COUNT=0

if %UPDATE_COUNT% GTR 0 (
    echo [!] New update found on Github!
    
    :: Show popup via separate Python script
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
    echo [OK] Already up to date!
)

:start_program
echo.
echo =========================================
echo       Launching ExpressVPN...
echo =========================================

set "EVPN_EXE="
if exist "C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
if "%EVPN_EXE%"=="" if exist "C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
if "%EVPN_EXE%"=="" if exist "C:\Program Files (x86)\ExpressVPN\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files (x86)\ExpressVPN\ExpressVPN.exe"
if "%EVPN_EXE%"=="" if exist "C:\Program Files\ExpressVPN\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files\ExpressVPN\ExpressVPN.exe"

if "%EVPN_EXE%"=="" (
    echo [!] ExpressVPN not installed - รัน INSTALL-EXPRESSVPN.bat ก่อน:
    if exist "%~dp0INSTALL-EXPRESSVPN.bat" (
        echo     %~dp0INSTALL-EXPRESSVPN.bat
        choice /C YN /T 10 /D N /M "เปิด INSTALL-EXPRESSVPN.bat ตอนนี้เลย (Y=yes, N=skip, ไม่กด 10 วิ=skip)"
        if !errorlevel! equ 1 (
            call "%~dp0INSTALL-EXPRESSVPN.bat"
        )
    ) else (
        echo     INSTALL-EXPRESSVPN.bat ไม่พบในโฟลเดอร์นี้
    )
) else (
    tasklist /FI "IMAGENAME eq ExpressVPN.exe" 2>nul | find /I "ExpressVPN.exe" >nul
    if errorlevel 1 (
        echo [*] starting: %EVPN_EXE%
        start "" "%EVPN_EXE%"
        echo [*] waiting 8s for ExpressVPN to boot...
        timeout /t 8 /nobreak >nul
    ) else (
        echo [OK] ExpressVPN already running
    )
)

echo.
echo =========================================
echo       Launching swap_bot ^(VPN rotator^)...
echo =========================================
set "SWAP_EXE=%~dp0swap_bot\dist\swap_bot.exe"
if exist "%SWAP_EXE%" (
    tasklist /FI "IMAGENAME eq swap_bot.exe" 2>nul | find /I "swap_bot.exe" >nul
    if errorlevel 1 (
        echo [*] starting: %SWAP_EXE%
        start "" "%SWAP_EXE%"
    ) else (
        echo [OK] swap_bot already running
    )
) else (
    echo [SKIP] %SWAP_EXE% not found
)

echo.
echo =========================================
echo       Starting program...
echo =========================================
echo.

python login.py
pause
