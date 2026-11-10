@echo off
setlocal

set "SER=127.0.0.1:7555"
set "OUT=C:\Users\Administrator\Downloads\LGR\api\jar"

echo ============================================================
echo   PULL-JAR - ดึง dynamic jar ที่ app โหลด runtime
echo ============================================================
echo.

if not exist "%OUT%" mkdir "%OUT%"

echo [1] find jar in app files ...
adb -s %SER% shell "su -c 'find /data/user/0/com.linecorp.LGRGS/files -name \"*.jar\" 2>/dev/null'"

echo.
echo [2] copy to sdcard (su needed) ...
adb -s %SER% shell "su -c 'find /data/user/0/com.linecorp.LGRGS/files -name \"*.jar\" -exec cp {} /sdcard/ \;'"
adb -s %SER% shell "su -c 'chmod 644 /sdcard/*.jar'"

echo.
echo [3] list on sdcard ...
adb -s %SER% shell "ls -la /sdcard/*.jar"

echo.
echo [4] pull ALL jar ...
adb -s %SER% pull /sdcard/ "%OUT%\" 2>&1 | findstr ".jar"

echo.
echo [5] list on PC ...
dir /b "%OUT%\*.jar"

echo.
echo [6] rename obfuscated name to simple name ...
for %%F in ("%OUT%\*.jar") do (
    set "fn=%%~nxF"
    echo processing: %%~nxF
)

echo.
echo [7] extract + list classes (ต้องมี jar command หรือ 7-Zip) ...
"C:\Program Files\7-Zip\7z.exe" l "%OUT%\*.jar" 2>nul | findstr ".class"

pause
