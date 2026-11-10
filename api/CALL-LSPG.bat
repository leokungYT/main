@echo off
setlocal

set "REPO=C:\Users\Administrator\Downloads\LGR"
set "SER=127.0.0.1:7555"
set "HOOK=%REPO%\api\frida_call_lspg.js"

echo ============================================================
echo   CALL-LSPG (python runner, no timeout)
echo ============================================================
echo.
echo   1) เปิด LGR ใน MuMu ถึง title/Main Stage
echo   2) อย่าปิด
echo   3) กด Enter
echo.
pause

echo [1] ensure renamed frida-server ...
adb -s %SER% shell "su -c 'pgrep fs >/dev/null || /data/local/tmp/fs -l 0.0.0.0:27043 &'"
adb -s %SER% forward tcp:27043 tcp:27043 >nul

echo [2] run via python ...
echo.
cd /d "%REPO%"
python api\run_frida.py api\frida_call_lspg.js

pause
