@echo off
setlocal

set "SER=127.0.0.1:7555"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\jar"

echo ============================================================
echo   PULL-JAR2 - rename unicode จาก emu ก่อน
echo ============================================================
echo.

if not exist "%OUT%" mkdir "%OUT%"

echo [1] rename + copy inside emu (wildcard หลบ unicode) ...
adb -s %SER% shell "su -c 'rm -f /sdcard/mystery.jar; cp /data/user/0/com.linecorp.LGRGS/files/.7a313957/*.jar /sdcard/mystery.jar; chmod 644 /sdcard/mystery.jar; ls -la /sdcard/mystery.jar'"

echo.
echo [2] pull simple name ...
adb -s %SER% pull /sdcard/mystery.jar "%OUT%\mystery.jar"

echo.
echo [3] also pull from subdirectory fca04b66 ...
adb -s %SER% shell "su -c 'find /data/user/0/com.linecorp.LGRGS/files -name \"*.jar\" -exec cp {} /sdcard/mystery2.jar \;; chmod 644 /sdcard/mystery2.jar; ls -la /sdcard/mystery2.jar'" 2>nul
adb -s %SER% pull /sdcard/mystery2.jar "%OUT%\mystery2.jar" 2>nul

echo.
echo [4] list ...
dir /b "%OUT%"

echo.
echo [5] list classes inside jar (ต้องมี 7-Zip) ...
"C:\Program Files\7-Zip\7z.exe" l "%OUT%\mystery.jar" 2>nul | findstr ".class" | more

pause
