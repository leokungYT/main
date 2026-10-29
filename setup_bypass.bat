@echo off
chcp 65001 >nul
REM =====================================================================
REM  LGR Bot - One-Click Bypass Setup (3.5.2)
REM  Built by Olivia - https://discord.gg/ojailbreaks
REM =====================================================================

setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo.
echo =============================================
echo   LGR Bypass Setup v3.5.2
echo =============================================
echo.

REM --- 0) python + adb -----------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found - install from python.org
    pause & exit /b 1
)

set "ADB=adb"
if exist "adb\adb.exe" set "ADB=%cd%\adb\adb.exe"
if exist "C:\Users\t\Desktop\main\adb\adb.exe" set "ADB=C:\Users\t\Desktop\main\adb\adb.exe"
where %ADB% >nul 2>&1
if errorlevel 1 (
    if not exist "%ADB%" (
        echo [ERROR] adb not found
        pause & exit /b 1
    )
)
echo [OK] adb = %ADB%
echo.

REM --- 1) pip install -------------------------------------------------
echo [1/5] Installing mitmproxy + frida-tools...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install mitmproxy frida-tools requests
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause & exit /b 1
)
echo [OK] packages installed
echo.

REM --- 2) locate mitmdump path (for login.py to call later) ----------
for /f "delims=" %%P in ('python -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2^>nul') do set "PYSCRIPTS=%%P"
set "MITMDUMP=!PYSCRIPTS!\mitmdump.exe"
if not exist "!MITMDUMP!" (
    for /f "delims=" %%P in ('python -c "import site; print(site.USER_BASE + r'\Scripts')" 2^>nul') do (
        if exist "%%P\mitmdump.exe" set "MITMDUMP=%%P\mitmdump.exe"
    )
)
if not exist "!MITMDUMP!" (
    for /f "delims=" %%M in ('where mitmdump 2^>nul') do set "MITMDUMP=%%M"
)
if not exist "!MITMDUMP!" set "MITMDUMP=%APPDATA%\Python\Python311\Scripts\mitmdump.exe"
if not exist "!MITMDUMP!" (
    echo [ERROR] mitmdump.exe not found after pip install
    pause & exit /b 1
)
echo [OK] mitmdump = !MITMDUMP!
echo.

REM --- 3) frida-server ------------------------------------------------
echo [2/5] frida-server (android-x86_64)...
if not exist "tools" mkdir tools
if exist "tools\frida-server" (
    echo [SKIP] already present
) else (
    python -c "import frida, urllib.request, lzma, os; v=frida.__version__; url=f'https://github.com/frida/frida/releases/download/{v}/frida-server-{v}-android-x86_64.xz'; print('  '+url); urllib.request.urlretrieve(url, 'tools/frida-server.xz'); open('tools/frida-server','wb').write(lzma.decompress(open('tools/frida-server.xz','rb').read())); os.remove('tools/frida-server.xz'); print('  done')"
    if errorlevel 1 (
        echo [WARN] auto-download failed - get it from github.com/frida/frida/releases
    ) else (
        echo [OK] frida-server ready
    )
)
echo.

REM --- 4) create CA directly via Python API (no mitmdump spawn) -------
echo [3/5] Generating mitmproxy CA via Python API...
set "CERT=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
if exist "%CERT%" (
    echo [SKIP] CA already exists
) else (
    python -c "import os; from mitmproxy.certs import CertStore; d=os.path.expanduser('~/.mitmproxy'); os.makedirs(d, exist_ok=True); CertStore.create_store(d, 'mitmproxy', 2048); print('  CA created')"
    if errorlevel 1 (
        echo [WARN] CertStore API failed - trying mitmdump fallback (15s)...
        start "" /B "!MITMDUMP!" --listen-port 8888 --set console_eventlog_verbosity=error
        timeout /t 15 /nobreak >nul
        taskkill /F /IM mitmdump.exe >nul 2>&1
    )
    if exist "%CERT%" (
        echo [OK] CA ready
    ) else (
        echo [ERROR] CA not generated. Try manually:
        echo         "!MITMDUMP!" --listen-port 8888
        echo        wait 10s, Ctrl+C, rerun this bat
        pause & exit /b 1
    )
)
echo.

REM --- 5) compute OpenSSL subject_hash_old via Python -----------------
echo [4/5] Pushing CA to MuMu emulators...
set "HASH="
for /f "delims=" %%H in ('python -c "import os, hashlib; from cryptography import x509; from cryptography.hazmat.primitives.serialization import Encoding; d=open(os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.cer'),'rb').read(); c=x509.load_pem_x509_certificate(d); sub=c.subject.public_bytes(); h=hashlib.md5(sub).digest(); print('%%08x' %% int.from_bytes(h[:4],'little'))" 2^>nul') do set "HASH=%%H"

if "!HASH!"=="" (
    echo [WARN] hash calc failed - using fallback c8750f0d
    set "HASH=c8750f0d"
)
echo        hash: !HASH!
set "CERT_NAME=!HASH!.0"
echo.

REM --- 6) push to every emulator --------------------------------------
set "PUSHED=0"
set "DEV_LIST=%TEMP%\lgr_devs.txt"
"%ADB%" devices > "%DEV_LIST%" 2>nul

for /f "tokens=1" %%D in ('type "%DEV_LIST%" ^| findstr /R "emulator\- 127\.0\.0\.1:"') do (
    set "DEV=%%D"
    echo    push -^> !DEV!
    "%ADB%" -s !DEV! push "%CERT%" /sdcard/mitmproxy-ca.cer >nul 2>&1
    "%ADB%" -s !DEV! root >nul 2>&1
    timeout /t 1 /nobreak >nul
    "%ADB%" -s !DEV! remount >nul 2>&1
    "%ADB%" -s !DEV! shell "mount -o remount,rw /" >nul 2>&1
    "%ADB%" -s !DEV! shell "mount -o remount,rw /system" >nul 2>&1
    "%ADB%" -s !DEV! shell "cp /sdcard/mitmproxy-ca.cer /system/etc/security/cacerts/!CERT_NAME!" >nul 2>&1
    "%ADB%" -s !DEV! shell "chmod 644 /system/etc/security/cacerts/!CERT_NAME!" >nul 2>&1
    "%ADB%" -s !DEV! shell "mkdir -p /data/misc/user/0/cacerts-added" >nul 2>&1
    "%ADB%" -s !DEV! shell "cp /sdcard/mitmproxy-ca.cer /data/misc/user/0/cacerts-added/!CERT_NAME!" >nul 2>&1
    "%ADB%" -s !DEV! shell "chmod 644 /data/misc/user/0/cacerts-added/!CERT_NAME!" >nul 2>&1
    set /A PUSHED+=1
)
del "%DEV_LIST%" 2>nul

if !PUSHED!==0 (
    echo [WARN] no emulators found - open MuMu first, then rerun
) else (
    echo [OK] pushed to !PUSHED! emulator(s)
)
echo.

REM --- 7) reboot ------------------------------------------------------
echo [5/5] Rebooting emulators...
"%ADB%" devices > "%DEV_LIST%" 2>nul
for /f "tokens=1" %%D in ('type "%DEV_LIST%" ^| findstr /R "emulator\- 127\.0\.0\.1:"') do (
    "%ADB%" -s %%D reboot >nul 2>&1
    echo    reboot %%D
)
del "%DEV_LIST%" 2>nul
echo.

REM --- 8) save mitmdump path -----------------------------------------
set "MITMDUMP_JSON=!MITMDUMP:\=\\!"
> bypass_paths.json echo { "mitmdump_exe": "!MITMDUMP_JSON!" }
echo [OK] saved bypass_paths.json
echo.

echo =============================================
echo   SETUP COMPLETE
echo =============================================
echo.
echo  Done:
echo    [v] mitmproxy + frida-tools
echo    [v] tools\frida-server
echo    [v] CA pushed to !PUSHED! emulator(s)
echo    [v] rebooting
echo    [v] bypass_paths.json saved
echo.
echo  Next: edit configmain.json ->
echo    "blind_mode": 1, "mitm_bypass": 1, "frida_bypass": 1,
echo    "mobile_spoof": 1, "wg_enabled": 0, "wg_lock": 1
echo.
echo  Built by Olivia - https://discord.gg/ojailbreaks
echo.
pause
endlocal
