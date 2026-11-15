@echo off
REM install-wireproxy.bat - download wireproxy.exe (userspace WireGuard with SOCKS5/HTTP proxy)
REM used by host_wg_pool.py for multi-IP pool mode (each proxy = different WG tunnel)

cd /d "%~dp0"

if exist wireproxy.exe (
    echo [WP] wireproxy.exe already present
    pause
    exit /b 0
)

set "WP_URL=https://github.com/pufferffish/wireproxy/releases/latest/download/wireproxy_windows_amd64.zip"
set "WP_ZIP=%TEMP%\wireproxy.zip"
set "WP_DIR=%TEMP%\wireproxy_extract"

echo [WP] Downloading wireproxy from %WP_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WP_URL%' -OutFile '%WP_ZIP%' -UseBasicParsing; Write-Host '[WP] download done' } catch { Write-Host ('[WP] download failed: ' + $_.Exception.Message); exit 1 }"

if not exist "%WP_ZIP%" (
    echo [WP] download failed - try manual download from %WP_URL%
    pause
    exit /b 1
)

echo [WP] Extracting...
if exist "%WP_DIR%" rmdir /s /q "%WP_DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%WP_ZIP%' -DestinationPath '%WP_DIR%' -Force"

REM find wireproxy.exe inside extract dir (binary location varies by release)
for /r "%WP_DIR%" %%f in (wireproxy.exe) do (
    copy /y "%%f" "%~dp0wireproxy.exe" >nul
    echo [WP] Copied: %%f -^> %~dp0wireproxy.exe
    goto :done
)

echo [WP] wireproxy.exe not found inside the zip
pause
exit /b 1

:done
del /q "%WP_ZIP%" >nul 2>&1
rmdir /s /q "%WP_DIR%" >nul 2>&1
echo.
echo [WP] wireproxy.exe installed OK at %~dp0wireproxy.exe
echo [WP] Now you can enable pool mode with: enable-host-vpn-pool.bat
pause
