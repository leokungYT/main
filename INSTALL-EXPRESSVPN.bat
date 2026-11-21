@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   INSTALL-EXPRESSVPN - download + install ExpressVPN (Windows)
echo ============================================================
echo.

rem --- check if already installed ---
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
    goto show_creds
)

echo [*] ExpressVPN not found - downloading installer...
echo.

set "INSTALLER=%TEMP%\expressvpn_installer.exe"
set "URL=https://www.expressvpn.com/clients/latest/windows"

powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%URL%' -OutFile '%INSTALLER%' -UseBasicParsing -MaximumRedirection 10; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] Download failed - get installer manually from:
    echo     %URL%
    pause
    exit /b 1
)

echo [*] Downloaded: %INSTALLER%
echo.
echo [*] Launching installer. Click UAC Yes.
echo     - Install with default settings.
echo     - After install, ExpressVPN login window should appear.
start "" "%INSTALLER%"

echo.
echo [*] Press Enter here AFTER you see the ExpressVPN "Sign In" window...
pause >nul

:show_creds
echo.
echo ============================================================
echo [STEP 1] Login ExpressVPN with these credentials (copy-paste)
echo ============================================================
if exist evpn_creds.txt (
    type evpn_creds.txt
) else (
    echo [!] evpn_creds.txt not found - enter email/password manually
)
echo.
echo ============================================================
echo [STEP 2] After login, connect to any country
echo ============================================================
echo.
echo [*] Done - next time loginสะสม.bat will auto-launch ExpressVPN + swap_bot
echo.
pause
endlocal
exit /b 0
