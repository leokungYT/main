@echo off
setlocal

echo ============================================================
echo   CALL-SCANDUMP - scan + dump raw bytes เป็นไฟล์
echo ============================================================
echo.
echo   1) LGR ที่ Main Stage ค้างไว้
echo   2) ก่อนรัน คลิก Shop หรือ Gacha ให้มี HTTP traffic สด
echo   3) กด Enter
echo.
pause

echo [1] run dumper ...
python C:\Users\Administrator\Downloads\LGR\api\run_frida_dump.py C:\Users\Administrator\Downloads\LGR\api\frida_scan_mem.js

pause
