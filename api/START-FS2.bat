@echo off
setlocal

set "SER=127.0.0.1:7555"

echo ============================================================
echo   START-FS2 - inline command, no shell script
echo ============================================================
echo.

echo [0] kill ...
adb -s %SER% shell "su -c 'pkill -9 fs; pkill -9 frida-server; rm -f /data/local/tmp/fs.log'"
timeout /t 1 /nobreak >nul

echo [1] convert CRLF -> LF ของ script (เผื่อ)
adb -s %SER% shell "su -c 'tr -d \"\\r\" < /data/local/tmp/start-fs.sh > /data/local/tmp/sf.sh; chmod 755 /data/local/tmp/sf.sh'"

echo [2] start fs inline ...
adb -s %SER% shell "su -c 'nohup /data/local/tmp/fs -l 0.0.0.0:27043 > /data/local/tmp/fs.log 2>&1 &'"
timeout /t 3 /nobreak >nul

echo [3] verify ...
adb -s %SER% shell "ps -A | grep -i -E '/fs|frida'"

echo.
echo [4] log tail ...
adb -s %SER% shell "cat /data/local/tmp/fs.log 2>/dev/null"

echo.
echo [5] netstat ...
adb -s %SER% shell "su -c 'netstat -lnt 2>/dev/null | grep 27043'"

echo.
echo [6] test fs binary runs manually (shows version) ...
adb -s %SER% shell "su -c '/data/local/tmp/fs --version'"

echo.
echo [7] check binary exists + executable ...
adb -s %SER% shell "ls -la /data/local/tmp/fs"
adb -s %SER% shell "file /data/local/tmp/fs 2>/dev/null"

echo.
echo [8] forward + python ping ...
adb -s %SER% forward --remove-all >nul 2>&1
adb -s %SER% forward tcp:27043 tcp:27043
python -c "import frida; d=frida.get_device_manager().add_remote_device('127.0.0.1:27043'); p=d.enumerate_processes(); print(f'OK total={len(p)}')" 2>&1

pause
