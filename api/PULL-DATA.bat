@echo off
setlocal

set "SER=127.0.0.1:7555"
set "PKG=com.linecorp.LGRGS"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\pulled"

echo ============================================================
echo   PULL-DATA - ดึงไฟล์ของ LGR ตรงจาก /data/data (ต้อง root)
echo ============================================================
echo.

if not exist "%OUT%" mkdir "%OUT%"

echo [1] reconnect adb ...
adb connect %SER% >nul

echo [2] copy files ออกมาที่ /sdcard/ ก่อน (su cp) ...
adb -s %SER% shell "su -c 'rm -rf /sdcard/lgr_dump; mkdir /sdcard/lgr_dump; cp -r /data/data/%PKG%/shared_prefs /sdcard/lgr_dump/; cp -r /data/data/%PKG%/databases /sdcard/lgr_dump/ 2>/dev/null; cp -r /data/data/%PKG%/files /sdcard/lgr_dump/ 2>/dev/null; cp -r /data/data/%PKG%/cache /sdcard/lgr_dump/ 2>/dev/null; chmod -R 777 /sdcard/lgr_dump'"

echo [3] list what we got ...
adb -s %SER% shell "ls -laR /sdcard/lgr_dump"
echo.

echo [4] pull to PC ...
adb -s %SER% pull /sdcard/lgr_dump "%OUT%"

echo.
echo [5] cleanup ...
adb -s %SER% shell "rm -rf /sdcard/lgr_dump"

echo.
echo ============================================================
echo   DONE. check: %OUT%\lgr_dump\
echo ============================================================
dir "%OUT%\lgr_dump\shared_prefs" 2>nul
pause
