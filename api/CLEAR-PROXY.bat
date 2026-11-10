@echo off
setlocal

set "SER=127.0.0.1:7555"

echo ============================================================
echo   CLEAR-PROXY — ลบ proxy ใน MuMu ให้เน็ตกลับมาใช้ได้
echo ============================================================
echo.

echo [1] reconnect adb ...
adb connect %SER% >nul

echo [2] ลบ proxy ทุกชั้น ...
adb -s %SER% shell settings delete global http_proxy
adb -s %SER% shell settings delete global https_proxy
adb -s %SER% shell settings put global http_proxy :0
adb -s %SER% shell settings put global global_http_proxy_host ""
adb -s %SER% shell settings put global global_http_proxy_port 0
adb -s %SER% shell settings put global global_http_proxy_exclusion_list ""

echo [3] ตรวจ:
adb -s %SER% shell settings get global http_proxy
adb -s %SER% shell settings get global https_proxy

echo.
echo [4] restart network ของ MuMu ...
adb -s %SER% shell svc wifi disable
timeout /t 1 /nobreak >nul
adb -s %SER% shell svc wifi enable
timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo   DONE
echo.
echo   ถ้าเน็ตยังไม่กลับมา:
echo     1) เปิด MuMu
echo     2) Settings (เฟือง) ^> Network ^& Internet ^> Wi-Fi
echo     3) แตะค้างที่ชื่อ Wi-Fi
echo     4) Modify ^> Advanced ^> Proxy = None
echo     5) Save
echo.
echo   หรือ reboot MuMu ก็ได้:
echo     adb -s %SER% reboot
echo ============================================================
pause
