@echo off
setlocal

set "REPO=C:\Users\Administrator\Downloads\LGR"
set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "HOOK=%REPO%\api\frida_scan_all.js"
set "PORT=27043"

echo ============================================================
echo   GRAB-CREDS-HIDDEN - renamed frida-server + anti-detect
echo ============================================================
echo.

echo [1] adb reverse port forward ...
adb -s %SER% reverse --remove-all >nul 2>&1
adb -s %SER% forward tcp:%PORT% tcp:%PORT% >nul
adb connect %SER% >nul

echo [2] ensure renamed frida-server running ...
adb -s %SER% shell "su -c 'pgrep fs >/dev/null || /data/local/tmp/fs -l 0.0.0.0:%PORT% &'"
timeout /t 2 /nobreak >nul

echo [3] force-stop game first ...
adb -s %SER% shell am force-stop %PKG%
timeout /t 1 /nobreak >nul

echo [4] spawn game with hook via custom port ...
echo.
cd /d "%REPO%"
frida -H 127.0.0.1:%PORT% -f %PKG% -l "%HOOK%"

pause
