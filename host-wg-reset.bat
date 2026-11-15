@echo off
REM host-wg-reset.bat - clear all host VPN state (tunnels, pool, blacklist, trigger)
REM Use when: WG keys are dead, want fresh rotation state, or something stuck

cd /d "%~dp0"

echo [RESET] Stopping any running WG tunnels...
call host-wg-kill.bat >nul 2>&1

echo [RESET] Clearing host VPN state files...
if exist .host_wg_tunnels (
    rmdir /s /q .host_wg_tunnels
    echo   - .host_wg_tunnels\ removed
)
if exist host_wg_state.json (
    del /q host_wg_state.json
    echo   - host_wg_state.json removed
)
if exist .host_wg_trigger (
    del /q .host_wg_trigger
    echo   - .host_wg_trigger removed
)

echo [RESET] Clearing wg/ pool + blacklist...
if exist wg\.pool (
    rmdir /s /q wg\.pool
    echo   - wg\.pool\ removed
)
if exist wg\.blocked.json (
    del /q wg\.blocked.json
    echo   - wg\.blocked.json removed
)
if exist wg\.cooldown.json (
    del /q wg\.cooldown.json
    echo   - wg\.cooldown.json removed
)

echo.
echo [RESET] Done.
echo.
echo If handshake keeps failing on every .conf = your Windscribe keypair is DEAD.
echo To get fresh keys:
echo   1. Login https://windscribe.com/getconfig/wireguard
echo   2. Download a new .conf
echo   3. Replace wg\ip-chan\main-1\key1.conf (or wherever keypair is)
echo   4. Next bot start will regenerate 15 fresh configs from that key
echo.
pause
