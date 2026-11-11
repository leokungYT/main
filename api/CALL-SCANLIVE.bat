@echo off
setlocal

echo ============================================================
echo   CALL-SCANLIVE - scan RAM ทุก 0.5 วินาที นาน 2 นาที
echo              คลิก Shop/Gacha/Mission ขณะ scan
echo ============================================================
echo.
echo   1) LGR อยู่ที่ Main Stage
echo   2) กด Enter ใน cmd นี้
echo   3) ไปที่ MuMu → คลิก SHOP (ปุ่ม shop ล่าง) หรือ GIFTBOX
echo      → เกมจะยิง /shop /gift ทันที
echo   4) Script scan ซ้ำๆ จะจับ request ที่ยัง fresh อยู่ใน heap
echo.
pause

echo [1] start live scanner + dumper ...
python C:\Users\Administrator\Downloads\LGR\api\run_frida_dump.py C:\Users\Administrator\Downloads\LGR\api\frida_scan_live.js

pause
