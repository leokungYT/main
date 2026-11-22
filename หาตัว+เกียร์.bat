@echo off
chcp 65001 >nul
title Ranger Gear Bot Auto Update
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
    if exist "_check_update.py" (
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
        echo [UPDATE] _check_update.py not found. Downloading latest files automatically...
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
echo       Launching swap_bot.exe (IP rotator)...
echo =========================================

setlocal EnableDelayedExpansion
rem --- ถ้ามีรันอยู่แล้ว ข้ามเลย ---
tasklist /FI "IMAGENAME eq swap_bot.exe" /NH 2>nul | find /I "swap_bot.exe" >nul
if !errorlevel! equ 0 (
    echo [SWAP_BOT] already running - skip
    goto start_python
)

rem --- ค้นหา swap_bot.exe จากหลายที่ ---
set "SB="
set "S1=%~dp0swap_bot\dist\swap_bot.exe"
set "S2=%~dp0swap_bot\swap_bot.exe"
set "S3=%~dp0..\LGR\swap_bot\dist\swap_bot.exe"
set "S4=%USERPROFILE%\Downloads\LGR\swap_bot\dist\swap_bot.exe"
set "S5=%USERPROFILE%\Desktop\main\swap_bot\dist\swap_bot.exe"
if exist "!S1!" set "SB=!S1!"
if "!SB!"=="" if exist "!S2!" set "SB=!S2!"
if "!SB!"=="" if exist "!S3!" set "SB=!S3!"
if "!SB!"=="" if exist "!S4!" set "SB=!S4!"
if "!SB!"=="" if exist "!S5!" set "SB=!S5!"

if "!SB!"=="" (
    echo [SWAP_BOT] WARN: ไม่พบ swap_bot.exe ที่ไหนเลย - จะข้าม
) else (
    echo [SWAP_BOT] launching: !SB!
    for %%I in ("!SB!") do start "" /D "%%~dpI" "!SB!"
)
endlocal

:start_python
echo.
echo =========================================
echo       Starting program...
echo =========================================
echo.

python ranger-gear.py
pause
