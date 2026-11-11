@echo off
setlocal

echo ============================================================
echo   CALL-LSPG-SPAWN - kill เกม + spawn ใหม่ + hook ก่อน resume
echo ============================================================
echo.
echo   1) อย่าเปิด LGR เอง — script spawn ให้
echo   2) ถ้า LGR เปิดอยู่ จะโดน kill แล้ว spawn ใหม่
echo   3) hook ติดตั้ง + resume → เห็น decrypt ตั้งแต่ splash
echo.
pause

echo [1] python runner SPAWN ...
python C:\Users\Administrator\Downloads\LGR\api\run_frida_spawn.py C:\Users\Administrator\Downloads\LGR\api\frida_call_lspg.js

pause
