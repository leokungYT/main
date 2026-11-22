@echo off
title Ranger Gear Bot
cd /d "%~dp0"

echo =========================================
echo    Checking for updates (optional)...
echo =========================================
if not exist ".git" (
    echo [SKIP] Not a Git repo
    goto start_program
)
git fetch origin main >nul 2>&1
for /f "tokens=*" %%g in ('git rev-list HEAD...origin/main --count 2^>nul') do (set UPDATE_COUNT=%%g)
if "%UPDATE_COUNT%"=="" set UPDATE_COUNT=0
if %UPDATE_COUNT% GTR 0 (
    echo [UPDATE] %UPDATE_COUNT% new commits - pulling...
    git reset --hard origin/main >nul 2>&1
    git clean -f >nul 2>&1
    echo [DONE] Update complete
) else (
    echo [OK] Already up to date
)

:start_program
echo.
echo =========================================
echo    Launching swap_bot.py (IP rotator)
echo =========================================

setlocal EnableDelayedExpansion
wmic process where "name='python.exe' or name='pythonw.exe'" get CommandLine 2>nul | find /I "swap_bot.py" >nul
if !errorlevel! equ 0 (
    echo [SWAP_BOT] already running - skip
    goto start_python
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
    echo [SWAP_BOT] WARN: swap_bot.py not found anywhere - skip
) else (
    echo [SWAP_BOT] launching: pythonw !SB!
    for %%I in ("!SB!") do start "" /D "%%~dpI" pythonw "!SB!"
)
endlocal

:start_python
echo.
echo =========================================
echo    Starting ranger-gear.py
echo =========================================
echo.

if not exist "logs" mkdir "logs" >nul 2>&1
python ranger-gear.py 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath logs\ranger-gear-last.log -Append"
set "EXITCODE=%errorlevel%"
echo.
echo =========================================
echo    Python exited with code: %EXITCODE%
echo =========================================
if %EXITCODE% NEQ 0 (
    echo [!] ERROR: python crashed - full log: logs\ranger-gear-last.log
)
pause
exit /b %EXITCODE%
