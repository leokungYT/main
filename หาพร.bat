@echo off
chcp 65001 >nul
title Ranger Plus
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
    
    :: Show popup via separate Python script (if exists)
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
        echo [UPDATE] Auto-updating...
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
echo       Launching swap_bot.py (IP rotator)...
echo =========================================

setlocal EnableDelayedExpansion
wmic process where "name='python.exe' or name='pythonw.exe'" get CommandLine 2>nul | find /I "swap_bot.py" >nul
if !errorlevel! equ 0 (
    echo [SWAP_BOT] already running - skip
    goto start_python_hp
)
set "SB="
set "S1=%~dp0swap_bot\swap_bot.py"
set "S2=%~dp0swap_bot.py"
set "S3=%~dp0..\LGR\swap_bot\swap_bot.py"
set "S4=%USERPROFILE%\Downloads\LGR\swap_bot\swap_bot.py"
set "S5=%USERPROFILE%\Desktop\main\swap_bot\swap_bot.py"
if exist "!S1!" set "SB=!S1!"
if "!SB!"=="" if exist "!S2!" set "SB=!S2!"
if "!SB!"=="" if exist "!S3!" set "SB=!S3!"
if "!SB!"=="" if exist "!S4!" set "SB=!S4!"
if "!SB!"=="" if exist "!S5!" set "SB=!S5!"
if "!SB!"=="" (
    echo [SWAP_BOT] WARN: ไม่พบ swap_bot.py - ข้าม
) else (
    echo [SWAP_BOT] launching: pythonw !SB!
    for %%I in ("!SB!") do start "" /D "%%~dpI" pythonw "!SB!"
)
endlocal

:start_python_hp
echo.
echo =========================================
echo       Starting Ranger Plus...
echo =========================================
echo.

:: Run rangerplus.py
python rangerplus.py

if %errorlevel% neq 0 (
    echo.
    echo =========================================
    echo [ERROR] Program crashed! See error above.
    echo =========================================
)

cmd /k
