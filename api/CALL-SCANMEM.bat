@echo off
setlocal

echo ============================================================
echo   CALL-SCANMEM - frida attach + scan RAM (ไม่ hook, ไม่ครัช)
echo ============================================================
echo.
echo   1) เปิด LGR ให้ถึง Main Stage ก่อน (session active)
echo   2) อย่าปิดเกม
echo   3) กด Enter → script attach + scan memory
echo.
pause

echo [1] ล้าง iptables noise จากรอบก่อน ...
adb -s 127.0.0.1:7555 shell "su -c 'iptables -t nat -F OUTPUT 2>/dev/null'" >nul 2>&1

echo [2] run scanner + dumper (save to api\dumps\) ...
python C:\Users\Administrator\Downloads\LGR\api\run_frida_dump.py C:\Users\Administrator\Downloads\LGR\api\frida_scan_mem.js

pause
