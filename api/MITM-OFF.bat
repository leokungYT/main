@echo off
setlocal

set "SER=127.0.0.1:7555"

echo [1] flush iptables REDIRECT ...
adb -s %SER% shell "su -c 'iptables -t nat -F OUTPUT'"

echo [2] kill mitmweb ...
taskkill /f /im mitmdump.exe >nul 2>&1
taskkill /f /im mitmweb.exe >nul 2>&1

echo [3] remove reverse ...
adb -s %SER% reverse --remove-all >nul 2>&1

echo done
pause
