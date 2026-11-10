@echo off
setlocal

set "SER=127.0.0.1:7555"

echo ============================================================
echo   START-FS - push shell script + รัน fs เป็น daemon จริงๆ
echo ============================================================

echo [1] push script ...
adb -s %SER% push C:\Users\Administrator\Downloads\LGR\api\start-fs.sh /data/local/tmp/start-fs.sh
adb -s %SER% shell "su -c 'chmod 755 /data/local/tmp/start-fs.sh'"

echo [2] run as root ...
adb -s %SER% shell "su -c '/data/local/tmp/start-fs.sh'"

echo.
echo [3] verify ...
timeout /t 2 /nobreak >nul
adb -s %SER% shell "ps -A | grep -E '/fs|frida'"

echo.
echo [4] netstat port 27043 ...
adb -s %SER% shell "netstat -lnt 2>/dev/null | grep 27043"

echo.
echo [5] log tail ...
adb -s %SER% shell "cat /data/local/tmp/fs.log"

echo.
echo [6] forward + test connection ...
adb -s %SER% forward tcp:27043 tcp:27043
python -c "import frida; d=frida.get_device_manager().add_remote_device('127.0.0.1:27043'); p=d.enumerate_processes(); print(f'OK total={len(p)}'); [print(x.pid, x.name) for x in p[:5]]"

pause
