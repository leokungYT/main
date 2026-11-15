@echo off
chcp 65001 >nul 2>&1
REM host-wg-rotate.bat - รัน host WireGuard rotator (สลับ VPN ทุก N นาที)
REM เปิดค้างไว้ก่อนเริ่มบอท - ปิดทีเดียวเลิกบอทให้รัน host-wg-rotate.bat --stop
REM
REM ต้องรันเป็น Administrator (wireguard.exe /installtunnelservice ติดตั้ง Windows service)
REM ถ้าเปิดไม่ใช่ Admin -> จะ auto elevate (ขึ้น UAC prompt) ให้อัตโนมัติ

REM --- auto elevate เป็น Admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [HOST-WG] ต้องสิทธิ์ Administrator - กำลังขอ UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0' -ArgumentList '%*'"
    exit /b
)

setlocal
cd /d "%~dp0"

if /i "%~1"=="--stop" (
    python host_wg_rotator.py --stop
    echo.
    echo [HOST-WG] stop เสร็จ - ปิดหน้าต่างได้
    pause
    exit /b %ERRORLEVEL%
)

echo [HOST-WG] เริ่ม rotator (ปล่อยหน้าต่างนี้ค้างไว้)
echo [HOST-WG] ปิดด้วย Ctrl+C หรือรัน host-wg-rotate.bat --stop
python host_wg_rotator.py %*
echo.
echo [HOST-WG] rotator หยุดแล้ว - ปิดหน้าต่างได้
pause
