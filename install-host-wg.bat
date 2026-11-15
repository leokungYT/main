@echo off
chcp 65001 >nul 2>&1
REM install-host-wg.bat - ติดตั้ง WireGuard for Windows
REM ใช้กับ host_wg_rotator.py (VPN นอกเครื่อง - IP เดียวคุมทุกอีมูฯ)

set "WG_EXE=C:\Program Files\WireGuard\wireguard.exe"
if exist "%WG_EXE%" (
    echo [WG] WireGuard for Windows ติดตั้งอยู่แล้ว: "%WG_EXE%"
    echo [WG] ใช้งานได้เลย - รัน host-wg-rotate.bat
    pause
    exit /b 0
)

REM --- auto elevate เป็น Admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WG] ต้องสิทธิ์ Administrator - กำลังขอ UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

setlocal

set "WG_URL1=https://download.wireguard.com/windows-client/wireguard-installer.exe"
set "WG_URL2=https://download.wireguard.com/windows-client/wireguard-amd64-0.5.3.msi"
set "WG_TMP=%TEMP%\wireguard-installer.exe"
set "WG_TMP_MSI=%TEMP%\wireguard-amd64.msi"

echo [WG] โหลด installer จาก %WG_URL1% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WG_URL1%' -OutFile '%WG_TMP%' -UseBasicParsing; exit 0 } catch { Write-Host ('ERR: ' + $_.Exception.Message); exit 1 }"

if not exist "%WG_TMP%" goto :try_msi

echo [WG] ติดตั้งแบบ silent...
"%WG_TMP%" /S
timeout /t 8 /nobreak >nul

if exist "%WG_EXE%" goto :done

echo [WG] silent ไม่สำเร็จ - เปิด installer ให้กด Install เอง (จอจะขึ้น setup wizard)
"%WG_TMP%"

if exist "%WG_EXE%" goto :done

:try_msi
echo [WG] ลองโหลด MSI สำรอง: %WG_URL2%
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WG_URL2%' -OutFile '%WG_TMP_MSI%' -UseBasicParsing; exit 0 } catch { Write-Host ('ERR: ' + $_.Exception.Message); exit 1 }"

if exist "%WG_TMP_MSI%" (
    echo [WG] ติดตั้ง MSI...
    msiexec /i "%WG_TMP_MSI%" /qn /norestart
    timeout /t 8 /nobreak >nul
)

if exist "%WG_EXE%" goto :done

echo.
echo [WG] ====================================================
echo [WG] ติดตั้งไม่สำเร็จแบบอัตโนมัติ - ให้ลองวิธีมือ:
echo [WG]
echo [WG]   1) เปิดเบราว์เซอร์ไปที่ https://www.wireguard.com/install/
echo [WG]   2) โหลด "Download Windows Installer"
echo [WG]   3) รัน installer ที่โหลดมา กดต่อจนจบ
echo [WG]   4) ตรวจว่ามีไฟล์ %WG_EXE% แล้วรัน host-wg-rotate.bat ต่อได้เลย
echo [WG] ====================================================
echo.
pause
exit /b 1

:done
del /q "%WG_TMP%" "%WG_TMP_MSI%" >nul 2>&1
echo.
echo [WG] ติดตั้ง WireGuard for Windows สำเร็จ ✓
echo [WG] ต่อไป: ตั้ง "use_host_vpn": 1 ใน configmain.json แล้วรัน host-wg-rotate.bat
pause
exit /b 0
