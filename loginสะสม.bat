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
echo       Starting program...
echo =========================================
echo.

python login.py --cli
pause
