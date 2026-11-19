@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   SETUP PROTON - install ProtonVPN WG (auto)
echo ============================================================
echo.

rem --- drag-and-drop folder onto this .bat ---
if not "%~1"=="" (
    if exist "%~1" (
        echo [*] use path from argument: %~1
        set "SRC=%~1"
        goto run
    )
)

rem --- auto-search ---
echo [*] auto-search Proton .conf in:
echo     - current folder: proton-configs
echo     - %USERPROFILE%\Downloads: proton-configs
echo     - %USERPROFILE%\Desktop: proton-configs
echo     (any .conf in a proton-configs folder, or proton-*.conf anywhere)
echo.

set "FOUND="

rem priority 1: any folder named proton-configs with ANY .conf in it
call :scan_any "%~dp0proton-configs"
call :scan_any "%USERPROFILE%\Downloads\proton-configs"
call :scan_any "%USERPROFILE%\Desktop\proton-configs"

rem priority 2: fallback - look for proton-*.conf files anywhere common
call :scan_proton "%~dp0"
call :scan_proton "%USERPROFILE%\Downloads"
call :scan_proton "%USERPROFILE%\Desktop"

if not defined FOUND (
    echo [!] no .conf found in any proton-configs folder and no proton-*.conf anywhere
    echo.
    echo HOW TO USE:
    echo   1. download 15 Proton WG .conf from account.proton.me/vpn/WireGuard
    echo   2. put all .conf files in a folder named: proton-configs
    echo      recommended path: Downloads\proton-configs\
    echo   3. drag that folder onto SETUP-PROTON.bat
    echo      OR double-click SETUP-PROTON.bat (will auto-find)
    echo.
    pause
    exit /b 1
)
set "SRC=%FOUND%"

:run
echo.
echo ============================================================
echo [*] running: python install-proton-wg.py "%SRC%"
echo ============================================================
echo.
python install-proton-wg.py "%SRC%"
if errorlevel 1 (
    echo.
    echo [!] install failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] install OK - bot will auto-detect Proton mode
echo ============================================================
echo.
echo NEXT:
echo   1. close running bot (if any)
echo   2. run autoupdate-lg.bat or python login.py
echo   3. you should see: [CONFIG] auto-detect Proton mode ...
echo.
pause
endlocal
exit /b 0

rem priority 1: accept any .conf in a folder named proton-configs
:scan_any
if defined FOUND exit /b 0
if not exist "%~1" exit /b 0
for %%F in ("%~1\*.conf") do (
    if exist "%%~F" (
        if not defined FOUND (
            set "FOUND=%~1"
            echo [OK] found .conf in: %~1
        )
    )
)
exit /b 0

rem priority 2: look specifically for proton-*.conf (post-install naming)
:scan_proton
if defined FOUND exit /b 0
if not exist "%~1" exit /b 0
for %%F in ("%~1\proton-*.conf") do (
    if exist "%%~F" (
        if not defined FOUND (
            set "FOUND=%~1"
            echo [OK] found proton-*.conf in: %~1
        )
    )
)
exit /b 0
