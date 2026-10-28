@echo off
REM =====================================================================
REM  LGR Bot - One-Click Bypass Setup (3.5.1)
REM  Built by Olivia - https://discord.gg/ojailbreaks
REM =====================================================================
REM  ทำ:
REM    1) pip install mitmproxy + frida-tools
REM    2) ดาวน์โหลด frida-server-android-x86_64 ล่าสุด -> tools\frida-server
REM    3) รัน mitmdump 5 วิ สร้าง CA ที่ %USERPROFILE%\.mitmproxy
REM    4) push CA เข้าทุกจอ MuMu ที่ adb เห็น (ทั้งแบบ system cert และ user cert)
REM    5) reboot จอทั้งหมด
REM =====================================================================

setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo.
echo =============================================
echo   LGR Bypass Setup v3.5.1
echo =============================================
echo.

REM --- 0) check prerequisites -----------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python ไม่เจอ - ติดตั้งจาก python.org ก่อน แล้วรันไฟล์นี้ใหม่
    pause
    exit /b 1
)

set "ADB=adb"
if exist "adb\adb.exe" set "ADB=adb\adb.exe"
if exist "C:\Users\t\Desktop\main\adb\adb.exe" set "ADB=C:\Users\t\Desktop\main\adb\adb.exe"

where %ADB% >nul 2>&1
if errorlevel 1 (
    if not exist "%ADB%" (
        echo [ERROR] ไม่เจอ adb - ติดตั้ง Android Platform Tools หรือเช็กพาธ
        pause
        exit /b 1
    )
)
echo [OK] ใช้ adb จาก: %ADB%
echo.

REM --- 1) pip install -------------------------------------------------
echo [1/5] ติดตั้ง mitmproxy + frida-tools...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install mitmproxy frida-tools requests
if errorlevel 1 (
    echo [ERROR] pip install ล้มเหลว - เช็กเน็ตแล้วลองใหม่
    pause
    exit /b 1
)
echo [OK] pip packages ติดตั้งแล้ว
echo.

REM --- 2) download frida-server --------------------------------------
echo [2/5] ดาวน์โหลด frida-server ล่าสุด (android-x86_64)...
if not exist "tools" mkdir tools
if exist "tools\frida-server" (
    echo [SKIP] tools\frida-server มีอยู่แล้ว - ข้าม
) else (
    python -c "import frida, urllib.request, lzma, os, json, sys; v=frida.__version__; url=f'https://github.com/frida/frida/releases/download/{v}/frida-server-{v}-android-x86_64.xz'; print(f'  download {url}'); urllib.request.urlretrieve(url, 'tools/frida-server.xz'); open('tools/frida-server','wb').write(lzma.decompress(open('tools/frida-server.xz','rb').read())); os.remove('tools/frida-server.xz'); print('  done.')"
    if errorlevel 1 (
        echo [WARN] ดาวน์โหลด frida-server อัตโนมัติล้มเหลว
        echo        ไปโหลดเองจาก: https://github.com/frida/frida/releases
        echo        เอาไฟล์ frida-server-^<version^>-android-x86_64.xz แตก unzip
        echo        แล้ววางที่ tools\frida-server
        echo.
    ) else (
        echo [OK] frida-server พร้อม
    )
)
echo.

REM --- 3) create mitmproxy CA -----------------------------------------
echo [3/5] สร้าง mitmproxy CA ครั้งแรก...
set "CERT=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
if exist "%CERT%" (
    echo [SKIP] CA มีอยู่แล้ว: %CERT%
) else (
    echo        เปิด mitmdump 5 วิ ให้มันสร้าง cert ...
    start /B /MIN cmd /c "mitmdump --listen-port 8888 >nul 2>&1"
    timeout /t 5 /nobreak >nul
    taskkill /F /IM mitmdump.exe >nul 2>&1
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq mitmdump*" >nul 2>&1
    if exist "%CERT%" (
        echo [OK] สร้างแล้ว: %CERT%
    ) else (
        echo [WARN] ยังไม่เจอ CA - ลองรัน mitmdump ด้วยมือครั้งเดียว:
        echo         mitmdump --listen-port 8888
        echo        แล้วรันไฟล์นี้อีกรอบ
        pause
        exit /b 1
    )
)
echo.

REM --- 4) compute cert hash and push to every MuMu --------------------
echo [4/5] คำนวณ cert hash + push เข้าทุกจอ...
for /f "delims=" %%H in ('python -c "import subprocess,re,os; p=subprocess.run(['openssl','x509','-inform','PEM','-subject_hash_old','-in',os.environ['USERPROFILE']+r'\.mitmproxy\mitmproxy-ca-cert.cer'],capture_output=True,text=True); print(p.stdout.splitlines()[0] if p.stdout else '')" 2^>nul') do set "HASH=%%H"

if "!HASH!"=="" (
    echo        openssl ไม่เจอ - ใช้ fallback hash c8750f0d
    set "HASH=c8750f0d"
) else (
    echo        hash: !HASH!
)

set "CERT_NAME=!HASH!.0"
set "PUSHED=0"
set "FAILED=0"

for /f "tokens=1" %%D in ('%ADB% devices 2^>nul ^| findstr /R "emulator\- 127\.0\.0\.1:"') do (
    set "DEV=%%D"
    if not "!DEV!"=="List" (
        echo    push -^> !DEV!
        %ADB% -s !DEV! push "%CERT%" /sdcard/mitmproxy-ca.cer >nul 2>&1
        %ADB% -s !DEV! root >nul 2>&1
        timeout /t 1 /nobreak >nul
        %ADB% -s !DEV! remount >nul 2>&1
        %ADB% -s !DEV! shell "mount -o remount,rw /" >nul 2>&1
        %ADB% -s !DEV! shell "mount -o remount,rw /system" >nul 2>&1
        %ADB% -s !DEV! shell "cp /sdcard/mitmproxy-ca.cer /system/etc/security/cacerts/!CERT_NAME!" >nul 2>&1
        %ADB% -s !DEV! shell "chmod 644 /system/etc/security/cacerts/!CERT_NAME!" >nul 2>&1
        REM fallback: user cert
        %ADB% -s !DEV! shell "mkdir -p /data/misc/user/0/cacerts-added" >nul 2>&1
        %ADB% -s !DEV! shell "cp /sdcard/mitmproxy-ca.cer /data/misc/user/0/cacerts-added/!CERT_NAME!" >nul 2>&1
        %ADB% -s !DEV! shell "chmod 644 /data/misc/user/0/cacerts-added/!CERT_NAME!" >nul 2>&1
        set /A PUSHED+=1
    )
)

if !PUSHED!==0 (
    echo [WARN] ไม่เจอจอ MuMu - เปิด MuMu แล้วรันไฟล์นี้ใหม่
) else (
    echo [OK] push ไปทั้งหมด !PUSHED! จอ
)
echo.

REM --- 5) reboot all emulators ---------------------------------------
echo [5/5] reboot ทุกจอ...
for /f "tokens=1" %%D in ('%ADB% devices 2^>nul ^| findstr /R "emulator\- 127\.0\.0\.1:"') do (
    set "DEV=%%D"
    if not "!DEV!"=="List" (
        echo    reboot !DEV!
        %ADB% -s !DEV! reboot >nul 2>&1
    )
)
echo.

echo =============================================
echo   SETUP COMPLETE
echo =============================================
echo.
echo  ที่ทำไปแล้ว:
echo    [v] mitmproxy + frida-tools installed
echo    [v] tools\frida-server ready
echo    [v] CA pushed to !PUSHED! emulator(s)
echo    [v] emulators rebooting
echo.
echo  ขั้นต่อไป:
echo    1) รอ MuMu reboot เสร็จ ~1 นาที
echo    2) เปิด configmain.json ตั้ง:
echo         "blind_mode": 1, "mitm_bypass": 1, "frida_bypass": 1,
echo         "mobile_spoof": 1, "wg_enabled": 0, "wg_lock": 1
echo    3) รันบอต login.py ตามปกติ - bypass เปิดอัตโนมัติ
echo.
echo  Built by Olivia - https://discord.gg/ojailbreaks
echo.
pause
endlocal
