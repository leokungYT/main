@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   INSTALL-EXPRESSVPN - one-click installer + login helper
echo ============================================================
echo.

rem --- 1) check if already installed ---
set "EVPN_EXE="
set "P1=C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P2=C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P3=C:\Program Files (x86)\ExpressVPN\ExpressVPN.exe"
set "P4=C:\Program Files\ExpressVPN\ExpressVPN.exe"
if exist "!P1!" set "EVPN_EXE=!P1!"
if "!EVPN_EXE!"=="" if exist "!P2!" set "EVPN_EXE=!P2!"
if "!EVPN_EXE!"=="" if exist "!P3!" set "EVPN_EXE=!P3!"
if "!EVPN_EXE!"=="" if exist "!P4!" set "EVPN_EXE=!P4!"

if not "!EVPN_EXE!"=="" (
    echo [OK] ExpressVPN already installed: !EVPN_EXE!
    echo.
    goto launch_and_login
)

rem --- 2) download installer ---
echo [1/4] Downloading ExpressVPN installer...
set "INSTALLER=%TEMP%\expressvpn_installer.exe"
set "URL=https://www.expressvpn.com/clients/latest/windows"

powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%URL%' -OutFile '%INSTALLER%' -UseBasicParsing -MaximumRedirection 10; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] Download failed - get installer manually from:
    echo     %URL%
    pause
    exit /b 1
)
echo       downloaded: %INSTALLER%
echo.

rem --- 3) silent install (ExpressVPN NSIS installer supports /S) ---
echo [2/4] Installing silently... ^(takes 30-60 seconds^)
echo       Click UAC Yes if prompted
"%INSTALLER%" /S
if errorlevel 1 (
    echo [!] Silent install failed - try interactive
    start "" "%INSTALLER%"
    echo [*] Press Enter here AFTER install completes
    pause >nul
)

rem --- 4) wait for install to finish, find exe ---
echo [3/4] Waiting for ExpressVPN to appear...
for /l %%i in (1,1,60) do (
    if exist "!P1!" set "EVPN_EXE=!P1!" & goto found_exe
    if exist "!P2!" set "EVPN_EXE=!P2!" & goto found_exe
    if exist "!P3!" set "EVPN_EXE=!P3!" & goto found_exe
    if exist "!P4!" set "EVPN_EXE=!P4!" & goto found_exe
    timeout /t 2 /nobreak >nul
)
echo [!] ExpressVPN.exe not found after 2 min - install may have failed
pause
exit /b 1

:found_exe
echo       found: !EVPN_EXE!
echo.

:launch_and_login
echo [4/4] Launching ExpressVPN + loading credentials...

rem read email/password from local file
set "EMAIL="
set "PASSWORD="
if exist evpn_creds.txt (
    for /f "usebackq tokens=1,* delims==" %%a in ("evpn_creds.txt") do (
        if /i "%%a"=="email" set "EMAIL=%%b"
        if /i "%%a"=="password" set "PASSWORD=%%b"
    )
)

rem launch ExpressVPN (new or existing window)
tasklist /FI "IMAGENAME eq ExpressVPN.exe" 2>nul | find /I "ExpressVPN.exe" >nul
if !errorlevel! equ 1 start "" "!EVPN_EXE!"

echo.
echo ============================================================
echo [DONE] ExpressVPN launched - sign-in window should open
echo ============================================================
echo.
if not "!EMAIL!"=="" (
    rem copy email to clipboard for first step
    echo !EMAIL!| clip
    echo [CLIPBOARD] EMAIL copied to clipboard: !EMAIL!
    echo   -^> Click the email field in ExpressVPN, press Ctrl+V
    echo.
    pause >nul
    echo !PASSWORD!| clip
    echo [CLIPBOARD] PASSWORD copied to clipboard
    echo   -^> Click the password field, Ctrl+V, click "Sign In"
    echo.
    echo Press any key after you clicked "Sign In"...
    pause >nul
) else (
    echo [!] evpn_creds.txt not found - enter credentials manually
    pause
)

echo.
echo ============================================================
echo [ALL DONE] next time: just double-click loginสะสม.bat
echo              it will auto-launch ExpressVPN + swap_bot + bot
echo ============================================================
echo.
pause
endlocal
exit /b 0
