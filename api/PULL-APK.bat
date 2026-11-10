@echo off
setlocal

set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\apk"

echo ============================================================
echo   PULL-APK - ดึง APK + split libs ของ LGR ออกมาหา AES key
echo ============================================================
echo.

if not exist "%OUT%" mkdir "%OUT%"

echo [1] หา APK paths ...
for /f "tokens=*" %%A in ('adb -s %SER% shell pm path %PKG%') do (
    echo %%A
)

echo.
echo [2] pull APK files ...
for /f "tokens=2 delims=:" %%A in ('adb -s %SER% shell pm path %PKG%') do (
    set "P=%%A"
    setlocal enabledelayedexpansion
    set "P=!P:~0,-1!"
    for %%B in ("!P!") do set "FN=%%~nxB"
    echo pulling !P!
    adb -s %SER% pull "!P!" "%OUT%\!FN!"
    endlocal
)

echo.
echo [3] list .so files in base.apk + split_config.arm64_v8a.apk ...
echo.
cd /d "%OUT%"
for %%F in (*.apk) do (
    echo === %%F ===
    "C:\Program Files\7-Zip\7z.exe" l "%%F" "lib\*" 2>nul | findstr ".so"
)

echo.
echo ============================================================
echo   NEXT: extract lib + หา AES key
echo ============================================================
echo.
echo   1) extract libs:
echo      "C:\Program Files\7-Zip\7z.exe" x base.apk -olib_base lib
echo      "C:\Program Files\7-Zip\7z.exe" x split_config.arm64_v8a.apk -olib_arm64 lib
echo.
echo   2) หา AES-related strings:
echo      cd lib_arm64\lib\arm64-v8a
echo      strings libLGRGS.so  ^| findstr /i "aes key cipher"
echo.
echo   3) ถ้า string เจอ key hardcoded = copy ใส่ xml_fire.py
echo      ถ้าไม่เจอ = decompile .so ด้วย Ghidra/IDA
pause
