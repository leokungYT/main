@echo off
setlocal

set "SER=127.0.0.1:7555"

echo ============================================================
echo   FIX-NET - clear proxy + reboot MuMu
echo ============================================================

adb connect %SER% >nul
adb -s %SER% shell settings put global http_proxy :0
adb -s %SER% shell settings delete global http_proxy
adb -s %SER% shell settings delete global https_proxy
adb -s %SER% shell settings delete global global_http_proxy_host
adb -s %SER% shell settings delete global global_http_proxy_port

echo.
echo rebooting MuMu now ...
adb -s %SER% reboot

echo.
echo รอ MuMu บูตเสร็จ ~30 วินาที แล้วลองเล่นเน็ตดู
pause
