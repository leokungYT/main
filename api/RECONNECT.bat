@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   RECONNECT - ต่อ MuMu กลับ + ปลุก fs ใหม่
echo ============================================================
echo.

set "ADB=adb"
set "FOUND="

echo [1] kill-server ล้าง state ก่อน ...
%ADB% kill-server >nul 2>&1
timeout /t 1 /nobreak >nul
%ADB% start-server >nul 2>&1
timeout /t 1 /nobreak >nul

echo.
echo [2] scan MuMu adb port (7555 / 16384 / 5555 / 16416) ...
for %%P in (7555 16384 5555 16416 7556 16385 21503) do (
    echo    try 127.0.0.1:%%P ...
    %ADB% connect 127.0.0.1:%%P 2>nul | findstr /i "connected"
    if !errorlevel! equ 0 (
        set "FOUND=127.0.0.1:%%P"
        goto :got
    )
)

:got
if "%FOUND%"=="" (
    echo.
    echo [X] หา MuMu ไม่เจอ — เปิด MuMu แล้วรอให้ Android boot เสร็จ, ลองใหม่
    pause
    exit /b 1
)

echo.
echo [+] CONNECTED: %FOUND%
echo.

echo [3] confirm device online ...
%ADB% -s %FOUND% get-state

echo.
echo [4] kill old fs + start new ...
%ADB% -s %FOUND% shell "su -c 'pkill -9 fs; pkill -9 frida-server; rm -f /data/local/tmp/fs.log'" 2>nul
timeout /t 1 /nobreak >nul

%ADB% -s %FOUND% shell "su -c 'nohup /data/local/tmp/fs -l 0.0.0.0:27043 > /data/local/tmp/fs.log 2>&1 &'"
timeout /t 3 /nobreak >nul

echo.
echo [5] verify fs running ...
%ADB% -s %FOUND% shell "ps -A | grep -E '/fs' | grep -v grep"

echo.
echo [6] netstat ...
%ADB% -s %FOUND% shell "su -c 'netstat -lnt 2>/dev/null | grep 27043'"

echo.
echo [7] forward port 27043 ...
%ADB% -s %FOUND% forward --remove-all >nul 2>&1
%ADB% -s %FOUND% forward tcp:27043 tcp:27043

echo.
echo [8] python ping ...
python -c "import frida; d=frida.get_device_manager().add_remote_device('127.0.0.1:27043'); p=d.enumerate_processes(); print(f'OK total={len(p)}')"

echo.
echo ============================================================
echo   SER=%FOUND%  →  ถ้า OK total=... ให้ไปรัน CALL-LSPG.bat
echo ============================================================

rem เขียน current port ลงไฟล์ — scripts อื่นอ่านต่อ
echo %FOUND%> C:\Users\Administrator\Downloads\LGR\api\.current_ser

pause
