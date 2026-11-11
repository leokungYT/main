@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   FRIDA CIPHER HOOK + ANTI-DETECT
echo ============================================================
echo.

if "%ADB_SERIAL%"=="" set "ADB_SERIAL=127.0.0.1:7555"
echo target device  = %ADB_SERIAL%

if "%LGR_PKG%"=="" (
    echo [*] auto-detecting LINE Rangers package ...
    for /f "usebackq tokens=2 delims=:" %%p in (`adb -s %ADB_SERIAL% shell pm list packages ^| findstr /i "ranger lgr linegame"`) do (
        if "!LGR_PKG!"=="" set "LGR_PKG=%%p"
        echo    candidate: %%p
    )
    if "!LGR_PKG!"=="" (
        echo [!] no package matched ranger/lgr/linegame
        pause
        endlocal
        exit /b 1
    )
)
echo target package = %LGR_PKG%
echo.

echo [*] restarting frida-server on alt port (27477) to dodge port scan ...
adb -s %ADB_SERIAL% shell "su -c 'pkill -f /data/local/tmp/fs'" >nul 2>&1
timeout /t 1 /nobreak >nul
start "" /B adb -s %ADB_SERIAL% shell "su -c 'nohup /data/local/tmp/fs -l 0.0.0.0:27477 >/dev/null 2>&1 &'"
timeout /t 2 /nobreak >nul

echo [*] forwarding local 27477 -^> device 27477 ...
adb -s %ADB_SERIAL% forward tcp:27477 tcp:27477 >nul

echo.
echo [*] spawning via -H 127.0.0.1:27477 (bypass default port scan) ...
echo    (frida prompt opens - type  %%resume  then Enter)
echo    (type  exit  to quit; output mirrored to cipher.log)
echo.
frida -H 127.0.0.1:27477 -f "%LGR_PKG%" -l frida_antidetect.js -l frida_cipher_hook.js -o cipher.log

pause
endlocal
