@echo off
setlocal

set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"

echo ============================================================
echo   DIAG - เทสทีละขั้น หาจุดที่ค้าง
echo ============================================================
echo.

echo [TEST 1] adb connect
adb connect %SER%
echo.

echo [TEST 2] adb devices
adb devices
echo.

echo [TEST 3] adb shell echo hello
adb -s %SER% shell echo "hello from emu"
echo.

echo [TEST 4] check root
adb -s %SER% shell "id"
adb -s %SER% shell "su -c id"
echo.

echo [TEST 5] frida command version
frida --version
echo.

echo [TEST 6] check frida-server ไฟล์
adb -s %SER% shell ls -la /data/local/tmp/frida-server
echo.

echo [TEST 7] check frida-server กำลังรันอยู่หรือไม่
adb -s %SER% shell "ps -A | grep frida"
echo.

echo [TEST 8] frida เห็น device ไหม
frida-ls-devices
echo.

echo [TEST 9] frida ping emu
frida-ps -U
echo (ต้องเห็น process list — ถ้าว่างคือ frida-server ไม่รัน)
echo.

echo [TEST 10] check LGR กำลังรันอยู่ใน MuMu ไหม
adb -s %SER% shell "pidof %PKG%"
echo (ถ้าตอบว่าง = เกมไม่ได้เปิดใน MuMu)
echo.

echo ============================================================
echo   อ่าน output ด้านบน แล้วบอกว่าตกค้างที่ TEST ไหน
echo ============================================================
pause
