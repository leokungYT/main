@echo off
REM install-host-wg.bat - install WireGuard for Windows
REM (needed by host_wg_rotator.py - host-level VPN mode)

set "WG_EXE=C:\Program Files\WireGuard\wireguard.exe"
if exist "%WG_EXE%" (
    echo [WG] WireGuard for Windows already installed: "%WG_EXE%"
    echo [WG] Run host-wg-rotate.bat to start the rotator.
    pause
    exit /b 0
)

REM --- auto elevate to Admin (wrap in cmd /k so window stays no matter what) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WG] Need Administrator rights - requesting UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'cmd.exe' -ArgumentList '/k','""%~f0""'"
    exit /b
)

setlocal

echo.
echo ===============================================
echo   WireGuard for Windows installer
echo ===============================================
echo.

set "WG_URL=https://download.wireguard.com/windows-client/wireguard-installer.exe"
set "WG_MSI=https://download.wireguard.com/windows-client/wireguard-amd64-0.5.3.msi"
set "WG_TMP=%TEMP%\wireguard-installer.exe"
set "WG_TMP_MSI=%TEMP%\wireguard-amd64.msi"

del /q "%WG_TMP%" "%WG_TMP_MSI%" >nul 2>&1

echo [WG] Downloading installer from %WG_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WG_URL%' -OutFile '%WG_TMP%' -UseBasicParsing; Write-Host '[WG] download done' } catch { Write-Host ('[WG] download failed: ' + $_.Exception.Message) }"

if not exist "%WG_TMP%" (
    echo [WG] No installer file - trying MSI fallback...
    goto :try_msi
)

echo.
echo [WG] Opening installer - click "Install" in the setup wizard.
echo [WG] (Just click Next/Install through to the end, no settings needed)
echo.
start /wait "" "%WG_TMP%"

timeout /t 3 /nobreak >nul
if exist "%WG_EXE%" goto :done

echo.
echo [WG] Still don't see %WG_EXE% - trying MSI fallback...

:try_msi
echo [WG] Downloading MSI from %WG_MSI% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WG_MSI%' -OutFile '%WG_TMP_MSI%' -UseBasicParsing; Write-Host '[WG] download done' } catch { Write-Host ('[WG] download failed: ' + $_.Exception.Message) }"

if exist "%WG_TMP_MSI%" (
    echo [WG] Installing MSI silently...
    msiexec /i "%WG_TMP_MSI%" /qn /norestart
    timeout /t 8 /nobreak >nul
)

if exist "%WG_EXE%" goto :done

echo.
echo [WG] ====================================================
echo [WG] Auto-install failed - download it manually:
echo [WG]
echo [WG]   1. Open  https://www.wireguard.com/install/
echo [WG]   2. Click "Download Windows Installer"
echo [WG]   3. Run the installer, click Install
echo [WG]   4. Then run host-wg-rotate.bat
echo [WG] ====================================================
echo.
pause
exit /b 1

:done
del /q "%WG_TMP%" "%WG_TMP_MSI%" >nul 2>&1
echo.
echo [WG] ====================================================
echo [WG] WireGuard for Windows installed OK
echo [WG] File: %WG_EXE%
echo [WG]
echo [WG] Next:
echo [WG]   1. Set "use_host_vpn": 1 in configmain.json
echo [WG]   2. Run host-wg-rotate.bat (UAC will prompt again)
echo [WG] ====================================================
echo.
pause
exit /b 0
