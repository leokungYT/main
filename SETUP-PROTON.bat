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
echo [*] auto-search proton-*.conf in:
echo     - current folder + proton-configs
echo     - %USERPROFILE%\Downloads
echo     - %USERPROFILE%\Desktop
echo.

set "FOUND="
call :scan "%~dp0proton-configs"
call :scan "%~dp0"
call :scan "%USERPROFILE%\Downloads\proton-configs"
call :scan "%USERPROFILE%\Downloads"
call :scan "%USERPROFILE%\Desktop\proton-configs"
call :scan "%USERPROFILE%\Desktop"

if not defined FOUND (
    echo [!] no proton-*.conf found anywhere
    echo.
    echo HOW TO USE:
    echo   1. download 15 Proton WG .conf from account.proton.me/vpn/WireGuard
    echo   2. drag the folder onto SETUP-PROTON.bat
    echo      OR put .conf files in Downloads\proton-configs\ then run again
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

:scan
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
