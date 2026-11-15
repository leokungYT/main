@echo off
REM fetch-windscribe-keys.bat - auto-fetch fresh Windscribe .conf via their web API
REM Requires: windscribe_user / windscribe_pass in configmain.json
REM          OR env WINDSCRIBE_USER / WINDSCRIBE_PASS
REM          OR pass them: fetch-windscribe-keys.bat <user> <pass>

cd /d "%~dp0"

echo [WS] Fetching fresh Windscribe keypair + configs...
python wg_windscribe_fetch.py %*
if %errorlevel% neq 0 (
    echo.
    echo [WS] If API failed - use manual:
    echo   1. Open https://windscribe.com/getconfig/wireguard
    echo   2. Login + Generate + Download 3 times (different countries)
    echo   3. Rename and place:
    echo        wg\ip-chan\main-1\key1.conf
    echo        wg\ip-chan\main-2\key2.conf
    echo        wg\ip-chan\main-3\key3.conf
    echo.
    pause
    exit /b 1
)

echo.
echo [WS] Keys fetched. Clearing old state + restarting rotator...
call host-wg-reset.bat
pause
