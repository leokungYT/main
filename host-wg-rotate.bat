@echo off
REM host-wg-rotate.bat - รัน host WireGuard rotator (สลับ VPN ทุก N นาที)
REM เปิดค้างไว้ก่อนเริ่มบอท - ปิดทีเดียวเลิกบอทให้รัน host-wg-rotate.bat --stop

setlocal
cd /d "%~dp0"

if "%~1"=="--stop" (
    python host_wg_rotator.py --stop
    exit /b %ERRORLEVEL%
)

echo [HOST-WG] เริ่ม rotator (ปล่อยหน้าต่างนี้ค้างไว้)
echo [HOST-WG] ปิดด้วย Ctrl+C หรือรัน host-wg-rotate.bat --stop
python host_wg_rotator.py %*
