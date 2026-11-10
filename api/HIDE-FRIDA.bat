@echo off
setlocal

set "SER=127.0.0.1:7555"
set "OLDNAME=frida-server"
set "NEWNAME=fs"

echo ============================================================
echo   HIDE-FRIDA - rename frida-server + change default port
echo ============================================================
echo.

echo [1] kill existing frida-server ...
adb -s %SER% shell "su -c 'pkill -9 frida-server'" >nul 2>&1
adb -s %SER% shell "su -c 'pkill -9 fs'" >nul 2>&1

echo [2] rename binary ...
adb -s %SER% shell "su -c 'cp /data/local/tmp/%OLDNAME% /data/local/tmp/%NEWNAME%'"
adb -s %SER% shell "su -c 'chmod 755 /data/local/tmp/%NEWNAME%'"

echo [3] start renamed server on custom port 27043 (bg) ...
adb -s %SER% shell "su -c '/data/local/tmp/%NEWNAME% -l 0.0.0.0:27043 &'"
timeout /t 3 /nobreak >nul

echo [4] verify running ...
adb -s %SER% shell "ps -A | grep %NEWNAME%"

echo.
echo ============================================================
echo   DONE
echo   next: run GRAB-CREDS-HIDDEN.bat to attach via new port
echo ============================================================
pause
