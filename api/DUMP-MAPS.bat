@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   DUMP /proc/pid/maps of running LGRGS
echo ============================================================
echo.
echo prereqs:
echo   - MuMu alive + LINE Rangers OPEN at splash/login (no frida!)
echo   - frida-server NOT running (we want app's natural state)
echo.

if "%ADB_SERIAL%"=="" set "ADB_SERIAL=127.0.0.1:7555"

echo [*] killing frida-server (if any) ...
adb -s %ADB_SERIAL% shell "su -c 'pkill -9 -f /data/local/tmp/fs'" 2>nul
timeout /t 1 /nobreak >nul

echo [*] opening LINE Rangers (without frida) ...
adb -s %ADB_SERIAL% shell am start -n com.linecorp.LGRGS/.ApplicationActivity 2>nul
echo    (if that activity name is wrong, open the app manually in MuMu)
echo    waiting 8 seconds for app to load ...
timeout /t 8 /nobreak >nul

echo [*] finding pid ...
for /f "usebackq tokens=2" %%p in (`adb -s %ADB_SERIAL% shell "pidof com.linecorp.LGRGS"`) do set "PID=%%p"
for /f "usebackq delims=" %%p in (`adb -s %ADB_SERIAL% shell "pidof com.linecorp.LGRGS"`) do set "PID=%%p"
echo    pid = %PID%
if "%PID%"=="" (
    echo [!] could not find pid - is the app running?
    pause
    endlocal
    exit /b 1
)

echo [*] dumping maps -^> maps.txt ...
adb -s %ADB_SERIAL% shell "su -c 'cat /proc/%PID%/maps'" > maps.txt
for %%A in (maps.txt) do echo    bytes = %%~zA

echo.
echo [*] libs that look like anti-tamper (filter):
findstr /i "nprotect npki nshield shield anti tamper secure guard knox lgcore libz3 line.security" maps.txt
echo.
echo [*] first 20 lines of all loaded libs:
findstr /c:".so" maps.txt | sort /unique > libs.txt
for /f "usebackq delims=" %%l in (`more /E +0 libs.txt`) do (
    echo    %%l
)

echo.
echo done - send maps.txt and the filtered list
pause
endlocal
