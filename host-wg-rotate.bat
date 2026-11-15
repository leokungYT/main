@echo off
REM host-wg-rotate.bat - Windows-host WireGuard rotator launcher
REM Keep this window open while bots run. Stop with: host-wg-rotate.bat --stop

REM --- auto elevate to Admin (wireguard.exe /installtunnelservice needs it) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [HOST-WG] Need Administrator rights - requesting UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'cmd.exe' -ArgumentList '/k','""%~f0"" %*'"
    exit /b
)

cd /d "%~dp0"
chcp 65001 >nul 2>&1

if /i "%~1"=="--stop" (
    python host_wg_rotator.py --stop
    echo.
    echo [HOST-WG] stop done.
    pause
    exit /b %ERRORLEVEL%
)

echo [HOST-WG] rotator starting (leave this window open)
echo [HOST-WG] stop with Ctrl+C, or run: host-wg-rotate.bat --stop
python host_wg_rotator.py %*
echo.
echo [HOST-WG] rotator stopped.
pause
