@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   UNFREEZE MUMU + clean frida state
echo ============================================================
echo.

if "%ADB_SERIAL%"=="" set "ADB_SERIAL=127.0.0.1:7555"

echo [1] trying soft stop of LGRGS ...
adb -s %ADB_SERIAL% shell "su -c 'am force-stop com.linecorp.LGRGS'" 2>nul
adb -s %ADB_SERIAL% shell "su -c 'pkill -9 -f com.linecorp.LGRGS'" 2>nul

echo [2] kill frida-server ...
adb -s %ADB_SERIAL% shell "su -c 'pkill -9 -f /data/local/tmp/fs'" 2>nul

echo [3] drop adb port forward ...
adb -s %ADB_SERIAL% forward --remove tcp:27477 2>nul

echo [4] restart adb server ...
adb kill-server
timeout /t 1 /nobreak >nul
adb start-server
timeout /t 1 /nobreak >nul

echo [5] re-check devices ...
adb devices
echo.

echo ------------------------------------------------------------
echo if MuMu window is still frozen on the host:
echo   - Task Manager -^> End task on MuMuPlayer / NemuPlayer
echo   - restart MuMu Player manually
echo ------------------------------------------------------------
pause
endlocal
