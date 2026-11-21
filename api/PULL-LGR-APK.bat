@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   PULL LINE Rangers APK from MuMu (no root needed)
echo   APK extracted here = api\lgr.apk
echo ============================================================
echo.

set "ADB=..\adb\adb.exe"
if not exist "%ADB%" set "ADB=adb"

if "%ADB_SERIAL%"=="" set "ADB_SERIAL=127.0.0.1:7555"
echo target device = %ADB_SERIAL%
echo.

echo [1] checking device online
"%ADB%" -s %ADB_SERIAL% get-state 2>nul
if errorlevel 1 (
    echo    not connected to %ADB_SERIAL% - trying "adb connect"
    "%ADB%" connect %ADB_SERIAL%
)
echo.

echo [2] locating com.linecorp.LGRGS on device
for /f "tokens=2 delims=:" %%p in ('"%ADB%" -s %ADB_SERIAL% shell pm path com.linecorp.LGRGS 2^>nul') do (
    set "APK_PATH=%%p"
    goto :found
)
echo [!] com.linecorp.LGRGS not installed on %ADB_SERIAL%
echo     install the game in MuMu first, then rerun
goto :end

:found
set "APK_PATH=%APK_PATH: =%"
echo    path on device: %APK_PATH%
echo.

echo [3] pulling APK to api\lgr.apk
"%ADB%" -s %ADB_SERIAL% pull "%APK_PATH%" lgr.apk
if errorlevel 1 (
    echo [!] pull failed
    goto :end
)
echo.

echo [4] checking split APKs (XAPK-style)
for /f "tokens=*" %%s in ('"%ADB%" -s %ADB_SERIAL% shell pm path com.linecorp.LGRGS 2^>nul') do (
    echo    %%s
)
echo.
echo [done] got lgr.apk
echo        next: py static_key_hunt.py --apk lgr.apk --xml ..\input-id\some.xml

:end
echo.
pause
endlocal
