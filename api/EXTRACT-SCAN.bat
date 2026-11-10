@echo off
setlocal

set "APKDIR=C:\Users\Administrator\Downloads\LGR\api\apk"
set "SZ=C:\Program Files\7-Zip\7z.exe"
set "PYSCRIPT=C:\Users\Administrator\Downloads\LGR\api\scan_aes_candidates.py"
set "ENC_BLOB=C:\Users\Administrator\Downloads\LGR\api\pulled\lgr_dump\shared_prefs\_LINE_COCOS_PREF_KEY.xml"

echo ============================================================
echo   EXTRACT-SCAN - extract .so + หา AES key candidates
echo ============================================================
echo.

if not exist "%SZ%" (
    echo [ERROR] 7-Zip ไม่เจอที่ %SZ%
    echo โหลด: https://www.7-zip.org/
    pause
    exit /b 1
)

echo [1] extract arm64 split ...
"%SZ%" x "%APKDIR%\split_config.arm64_v8a.apk" -o"%APKDIR%\arm64" -y lib >nul
echo.

echo [2] list .so files ...
dir /b "%APKDIR%\arm64\lib\arm64-v8a\"
echo.

echo [3] extract base.apk libs too (ถ้ามี) ...
"%SZ%" x "%APKDIR%\base.apk" -o"%APKDIR%\base" -y lib >nul 2>&1
if exist "%APKDIR%\base\lib" (
    dir /b /s "%APKDIR%\base\lib\*.so"
)
echo.

echo [4] scan .so หา AES key candidates (ใช้ python) ...
echo.
python "%PYSCRIPT%" "%APKDIR%\arm64\lib\arm64-v8a" "%ENC_BLOB%"

echo.
echo ============================================================
echo   DONE - ดู output ด้านบน
echo ============================================================
pause
