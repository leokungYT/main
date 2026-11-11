@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   BRUTE-KEY - sweep AES key patterns for _ENC_LF_AC
echo              seed "linegamesupersecret" + udid
echo ============================================================
echo.

echo [1] install pycryptodome if missing ...
python -m pip install --quiet pycryptodome >nul 2>&1

echo [2] udid sources ...
set "PULL_UDID="
if exist "_UDID.txt" (
  set /p PULL_UDID=<_UDID.txt
)
set "PULL_UDID=%PULL_UDID: =%"

set "ANDROID_ID="
for /f "usebackq delims=" %%i in (`adb shell settings get secure android_id 2^>nul`) do set "ANDROID_ID=%%i"
set "ANDROID_ID=%ANDROID_ID: =%"
set "ANDROID_ID=%ANDROID_ID:~0,32%"

echo    _DEVICE_UUID_KEY (XML) = %PULL_UDID%
echo    android_id       (adb) = %ANDROID_ID%

if "%PULL_UDID%"=="" if "%ANDROID_ID%"=="" (
  echo [!] no udid source found
  pause
  endlocal
  exit /b 1
)

echo [3] run brute ...
python -X utf8 -W ignore::DeprecationWarning BRUTE-KEY.py "%PULL_UDID%" "%ANDROID_ID%"

pause
endlocal
