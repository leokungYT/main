@echo off
setlocal

set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\apk"
set "APKDIR=/data/app/~~YzkkhIHrPvBGmUSRcr7_JA==/com.linecorp.LGRGS-rcQ7IfyXgeoD7Wu4WzCs0w=="

echo ============================================================
echo   PULL-APK2 - pull APK + split libs ตรง path hardcoded
echo ============================================================

if not exist "%OUT%" mkdir "%OUT%"

echo [1] pull base.apk ...
adb -s %SER% pull "%APKDIR%/base.apk" "%OUT%\base.apk"

echo [2] pull split_config.arm64_v8a.apk ...
adb -s %SER% pull "%APKDIR%/split_config.arm64_v8a.apk" "%OUT%\split_config.arm64_v8a.apk"

echo [3] pull split_config.en.apk ...
adb -s %SER% pull "%APKDIR%/split_config.en.apk" "%OUT%\split_config.en.apk"

echo [4] pull split_config.xhdpi.apk ...
adb -s %SER% pull "%APKDIR%/split_config.xhdpi.apk" "%OUT%\split_config.xhdpi.apk"

echo.
echo [5] list ...
dir "%OUT%"

echo.
echo ============================================================
echo   NEXT STEPS
echo ============================================================
echo.
echo 1) extract libs (ต้องมี 7-Zip):
echo    "C:\Program Files\7-Zip\7z.exe" x "%OUT%\split_config.arm64_v8a.apk" -o"%OUT%\arm64" lib
echo.
echo 2) จะได้โฟลเดอร์ %OUT%\arm64\lib\arm64-v8a\
echo    มี .so ทั้งหมดของเกม
echo.
echo 3) ผมจะเขียน script หา AES key ใน .so ให้ หลัง extract เสร็จ
pause
