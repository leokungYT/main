@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   SETUP FRIDA-SERVER on MuMu (root required)
echo ============================================================
echo.
echo prereqs:
echo   - MuMu root enabled (Settings -^> Preference -^> Other -^> Root)
echo   - adb connected (adb devices should show emulator-xxxx)
echo.

echo [*] adb devices ...
adb devices
echo.

python -X utf8 setup_frida_server.py

echo.
pause
endlocal
