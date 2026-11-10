@echo off
setlocal

set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "REPO=C:\Users\Administrator\Downloads\LGR"

echo ============================================================
echo   FRIDA-DIAG v2 - ไม่ค้างแล้ว
echo ============================================================
echo.

echo [1] kill all frida-server variants ...
adb -s %SER% shell "su -c 'pkill -9 frida-server'" >nul 2>&1
adb -s %SER% shell "su -c 'pkill -9 fs'" >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2] start fresh renamed server in background (PC side) ...
start "frida-server" /min cmd /c "adb -s %SER% shell su -c /data/local/tmp/fs -l 0.0.0.0:27043"
timeout /t 4 /nobreak >nul

echo [3] verify server process in emu ...
adb -s %SER% shell "ps -A | grep -E 'frida|/fs'"
echo.

echo [4] check port listening ...
adb -s %SER% shell "netstat -lnp 2>/dev/null | grep 27043"
echo.

echo [5] forward port ...
adb -s %SER% forward --remove-all >nul 2>&1
adb -s %SER% forward tcp:27043 tcp:27043
echo.

echo [6] frida enumerate processes ...
python -c "import frida; d=frida.get_device_manager().add_remote_device('127.0.0.1:27043'); procs=d.enumerate_processes(); print(f'total={len(procs)}'); [print(p.pid, p.name) for p in procs[:10]]"
echo.

echo [7] check LGR running ...
adb -s %SER% shell "pidof %PKG%"
echo.

echo [8] try bare test script attach ...
cd /d "%REPO%"
python api\run_frida.py api\bare_test.js

pause
