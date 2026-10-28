@echo off
chcp 65001 >nul
REM =====================================================================
REM  LGR Bot - One-Click Bypass Setup (3.5.1)
REM  Built by Olivia - https://discord.gg/ojailbreaks
REM =====================================================================

setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo.
echo =============================================
echo   LGR Bypass Setup v3.5.1
echo =============================================
echo.

REM --- 0) check python & adb -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found - install from python.org first
    pause
    exit /b 1
)

set "ADB=adb"
if exist "adb\adb.exe" set "ADB=%cd%\adb\adb.exe"
if exist "C:\Users\t\Desktop\main\adb\adb.exe" set "ADB=C:\Users\t\Desktop\main\adb\adb.exe"
where %ADB% >nul 2>&1
if errorlevel 1 (
    if not exist "%ADB%" (
        echo [ERROR] adb not found - install Android Platform Tools
        pause
        exit /b 1
    )
)
echo [OK] adb = %ADB%
echo.

REM --- 1) pip install --------------------------------------------------
echo [1/5] Installing mitmproxy + frida-tools...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install mitmproxy frida-tools requests
if errorlevel 1 (
    echo [ERROR] pip install failed - check internet
    pause
    exit /b 1
)
echo [OK] pip packages installed
echo.

REM --- 2) locate mitmdump / python Scripts dir ------------------------
REM scripts dir ของ pip install --user บน Python 3.11
for /f "delims=" %%P in ('python -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2^>nul') do set "PYSCRIPTS=%%P"
if "!PYSCRIPTS!"=="" (
    for /f "delims=" %%P in ('python -c "import site; print(site.USER_BASE + r'\Scripts')" 2^>nul') do set "PYSCRIPTS=%%P"
)
set "MITMDUMP=!PYSCRIPTS!\mitmdump.exe"
if not exist "!MITMDUMP!" (
    REM fallback: find any mitmdump.exe
    for /f "delims=" %%M in ('where mitmdump 2^>nul') do set "MITMDUMP=%%M"
)
if not exist "!MITMDUMP!" (
    REM final fallback: user scripts dir hardcoded
    set "MITMDUMP=%APPDATA%\Python\Python311\Scripts\mitmdump.exe"
)
if not exist "!MITMDUMP!" (
    echo [ERROR] mitmdump.exe not found. Try:
    echo         python -m pip install --force-reinstall mitmproxy
    pause
    exit /b 1
)
echo [OK] mitmdump = !MITMDUMP!
echo.

REM --- 3) download frida-server ---------------------------------------
echo [2/5] Downloading frida-server (android-x86_64)...
if not exist "tools" mkdir tools
if exist "tools\frida-server" (
    echo [SKIP] tools\frida-server already present
) else (
    python -c "import frida, urllib.request, lzma, os; v=frida.__version__; url=f'https://github.com/frida/frida/releases/download/{v}/frida-server-{v}-android-x86_64.xz'; print(f'  download {url}'); urllib.request.urlretrieve(url, 'tools/frida-server.xz'); open('tools/frida-server','wb').write(lzma.decompress(open('tools/frida-server.xz','rb').read())); os.remove('tools/frida-server.xz'); print('  done.')"
    if errorlevel 1 (
        echo [WARN] auto-download failed - get it manually from github.com/frida/frida/releases
        echo        place at tools\frida-server
    ) else (
        echo [OK] frida-server ready
    )
)
echo.

REM --- 4) create mitmproxy CA -----------------------------------------
echo [3/5] Creating mitmproxy CA...
set "CERT=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.cer"
if exist "%CERT%" (
    echo [SKIP] CA already exists: %CERT%
) else (
    echo        Starting mitmdump for 8s to generate cert...
    start "" /B "!MITMDUMP!" --listen-port 8888 -q
    timeout /t 8 /nobreak >nul
    taskkill /F /IM mitmdump.exe >nul 2>&1
    if exist "%CERT%" (
        echo [OK] CA created: %CERT%
    ) else (
        echo [WARN] CA not generated. Run manually once:
        echo         "!MITMDUMP!" --listen-port 8888
        echo        wait 5s, Ctrl+C, then rerun this script
        pause
        exit /b 1
    )
)
echo.

REM --- 5) compute cert hash -------------------------------------------
echo [4/5] Pushing CA to all MuMu emulators...
set "HASH="
where openssl >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%H in ('openssl x509 -inform PEM -subject_hash_old -in "%CERT%" 2^>nul ^| findstr /R "^[0-9a-f]"') do (
        if "!HASH!"=="" set "HASH=%%H"
    )
)
if "!HASH!"=="" (
    REM compute via python+cryptography (shipped with mitmproxy)
    for /f "delims=" %%H in ('python -c "from cryptography import x509; from cryptography.hazmat.primitives import hashes; import hashlib, os; d=open(os.environ['USERPROFILE']+r'\.mitmproxy\mitmproxy-ca-cert.cer','rb').read(); c=x509.load_pem_x509_certificate(d); n=c.subject.public_bytes(); import struct; h=hashlib.md5(n).digest()[:4]; print('%%02x%%02x%%02x%%02x' %% (h[3],h[2],h[1],h[0]))" 2^>nul') do set "HASH=%%H"
)
if "!HASH!"=="" (
    echo [WARN] cannot compute hash - using fallback c8750f0d
    set "HASH=c8750f0d"
)
echo        cert hash: !HASH!
set "CERT_NAME=!HASH!.0"

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
    echo [WARN] no MuMu emulators found - open MuMu first, then rerun
) else (
    echo [OK] pushed to !PUSHED! emulator(s)
)
echo.

REM --- 7) reboot ------------------------------------------------------
echo [5/5] Rebooting all emulators...
"%ADB%" devices > "%DEV_LIST%" 2>nul
for /f "tokens=1" %%D in ('type "%DEV_LIST%" ^| findstr /R "emulator\- 127\.0\.0\.1:"') do (
    set "DEV=%%D"
    echo    reboot !DEV!
    "%ADB%" -s !DEV! reboot >nul 2>&1
)
del "%DEV_LIST%" 2>nul
echo.

REM --- 8) save path hint for login.py --------------------------------
echo { "mitmdump_exe": "!MITMDUMP:\=\\!" } > bypass_paths.json
echo [OK] saved mitmdump path to bypass_paths.json
echo.

echo =============================================
echo   SETUP COMPLETE
echo =============================================
echo.
echo  Done:
echo    [v] mitmproxy + frida-tools installed
echo    [v] tools\frida-server ready
echo    [v] CA pushed to !PUSHED! emulator(s)
echo    [v] emulators rebooting
echo    [v] mitmdump path saved to bypass_paths.json
echo.
echo  Next:
echo    1) wait ~1min for MuMu reboot
echo    2) edit configmain.json:
echo         "blind_mode": 1, "mitm_bypass": 1, "frida_bypass": 1,
echo         "mobile_spoof": 1, "wg_enabled": 0, "wg_lock": 1,
echo         "mitmdump_exe": "!MITMDUMP:\=\\!"
echo    3) run login.py normally
echo.
echo  Built by Olivia - https://discord.gg/ojailbreaks
echo.
pause
endlocal
