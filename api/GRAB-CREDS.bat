@echo off
setlocal

set "REPO=C:\Users\Administrator\Downloads\LGR"
set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "HOOK=%REPO%\api\frida_scan_all.js"

echo ============================================================
echo   GRAB-CREDS - attach mode, native SSL hook
echo ============================================================
echo.
echo   ขั้นตอน:
echo     1) เปิด LGR ใน MuMu ให้ถึงหน้า title ก่อน (อย่าปิด!)
echo     2) กด Enter ที่นี่
echo     3) frida จะ attach + hook SSL_write/SSL_read
echo     4) เล่นเกมหรือกด login — จะเห็น POST /login โผล่
echo.
pause

echo [1] reconnect adb ...
adb connect %SER% >nul

echo [2] ensure frida-server running ...
adb -s %SER% shell "su -c 'pgrep frida-server >/dev/null || /data/local/tmp/frida-server &'"
timeout /t 2 /nobreak >nul

echo [3] spawn %PKG% with hook ...
echo.
cd /d "%REPO%"
frida -D %SER% -f %PKG% -l "%HOOK%"

pause
