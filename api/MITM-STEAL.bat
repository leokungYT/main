@echo off
setlocal

echo ============================================================
echo   MITM-STEAL v2 - scope iptables แค่ UID ของ LGR เท่านั้น
echo              ไม่โดน app อื่น (Facebook/Discord/etc)
echo ============================================================
echo.

set "SER=127.0.0.1:7555"
set "PORT=8080"
set "PKG=com.linecorp.LGRGS"
set "MITM_DIR=%USERPROFILE%\.mitmproxy"

echo [0] kill mitm เก่า + ล้าง iptables ...
taskkill /f /im mitmdump.exe >nul 2>&1
taskkill /f /im mitmweb.exe >nul 2>&1
adb -s %SER% shell "su -c 'iptables -t nat -F OUTPUT 2>/dev/null; iptables -t nat -F 2>/dev/null'" >nul 2>&1

echo.
echo [1] find LGR UID ...
for /f "tokens=2 delims==" %%u in ('adb -s %SER% shell "dumpsys package %PKG% ^| grep userId=" 2^>nul') do (
    for /f "tokens=1" %%v in ("%%u") do set "LGRUID=%%v"
    goto :got_uid
)
:got_uid
if "%LGRUID%"=="" (
    echo [X] หา UID ของ %PKG% ไม่เจอ — LGR install อยู่ไหม?
    pause
    exit /b 1
)
echo    LGR UID = %LGRUID%

echo.
echo [2] ensure mitmproxy CA exists ...
if not exist "%MITM_DIR%\mitmproxy-ca-cert.pem" (
    start /b mitmdump -q >nul 2>&1
    timeout /t 3 /nobreak >nul
    taskkill /f /im mitmdump.exe >nul 2>&1
)

echo.
echo [3] compute android cert hash + install to system trust ...
python -c "from cryptography.hazmat.backends import default_backend; from cryptography import x509; import hashlib; d=open(r'%MITM_DIR%\mitmproxy-ca-cert.pem','rb').read(); c=x509.load_pem_x509_certificate(d,default_backend()); subj=c.subject.public_bytes(default_backend()); print(hashlib.md5(subj).digest()[::-1].hex()[:8])" > ca_hash.tmp 2>nul
set /p CAHASH=<ca_hash.tmp
del ca_hash.tmp
if "%CAHASH%"=="" set "CAHASH=c8750f0d"
echo    CA hash = %CAHASH%.0

adb -s %SER% push "%MITM_DIR%\mitmproxy-ca-cert.pem" /sdcard/mitm-ca.pem >nul 2>&1
adb -s %SER% shell "su -c 'mount -o rw,remount /; mount -o rw,remount /system 2>/dev/null; cp /sdcard/mitm-ca.pem /system/etc/security/cacerts/%CAHASH%.0; chmod 644 /system/etc/security/cacerts/%CAHASH%.0'"
adb -s %SER% shell "ls -la /system/etc/security/cacerts/%CAHASH%.0"

echo.
echo [4] adb reverse %PORT% ...
adb -s %SER% reverse --remove-all >nul 2>&1
adb -s %SER% reverse tcp:%PORT% tcp:%PORT%

echo.
echo [5] iptables REDIRECT 443/80 → %PORT% SCOPED เฉพาะ UID %LGRUID% ...
adb -s %SER% shell "su -c 'iptables -t nat -F OUTPUT; iptables -t nat -A OUTPUT -p tcp --dport 443 -m owner --uid-owner %LGRUID% -j REDIRECT --to-ports %PORT%; iptables -t nat -A OUTPUT -p tcp --dport 80 -m owner --uid-owner %LGRUID% -j REDIRECT --to-ports %PORT%; iptables -t nat -L OUTPUT -n -v'"

echo.
echo [6] launch mitmweb (regular mode ไม่ transparent) ...
start "" mitmweb --mode regular --listen-port %PORT% --showhost --set console_eventlog_verbosity=info

echo.
echo [7] force-stop + start LGR ...
adb -s %SER% shell "am force-stop %PKG%"
timeout /t 1 /nobreak >nul
adb -s %SER% shell "monkey -p %PKG% -c android.intent.category.LAUNCHER 1" >nul 2>&1

echo.
echo ============================================================
echo   mitmweb @  http://127.0.0.1:8081
echo   จะเห็น flow เฉพาะ LGR (udid=%LGRUID%)
echo   รอ:  POST https://.../login
echo ============================================================
echo.
echo   พอได้ body → ดู "guestCookie" + "udid"
echo   แล้ว: python api\xml_fire.py --udid U --guest G --gift
echo.
echo   ปิด: api\MITM-OFF.bat
echo.
pause
