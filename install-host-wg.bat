@echo off
chcp 65001 >nul 2>&1
REM install-host-wg.bat - ติดตั้ง WireGuard for Windows แบบเงียบ
REM ใช้กับ host_wg_rotator.py (VPN นอกเครื่อง - IP เดียวคุมทุกอีมูฯ)

setlocal

set "WG_EXE=C:\Program Files\WireGuard\wireguard.exe"
if exist "%WG_EXE%" (
    echo [WG] WireGuard for Windows ติดตั้งอยู่แล้ว: "%WG_EXE%"
    echo [WG] ใช้งานได้เลย - รัน host-wg-rotate.bat หรือ python host_wg_rotator.py
    exit /b 0
)

set "WG_URL=https://download.wireguard.com/windows-client/wireguard-installer.exe"
set "WG_TMP=%TEMP%\wireguard-installer.exe"

echo [WG] กำลังโหลด installer จาก %WG_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%WG_URL%' -OutFile '%WG_TMP%' -UseBasicParsing } catch { Write-Host $_.Exception.Message; exit 1 }"
if not exist "%WG_TMP%" (
    echo [WG] โหลด installer ไม่สำเร็จ - เช็คเน็ตหรือโหลดเองจาก %WG_URL%
    exit /b 1
)

echo [WG] กำลังติดตั้ง (ต้องสิทธิ์ Admin)...
"%WG_TMP%" /quiet
set RC=%ERRORLEVEL%
del /q "%WG_TMP%" >nul 2>&1

if not exist "%WG_EXE%" (
    echo [WG] ติดตั้งไม่สำเร็จ (rc=%RC%) - รัน cmd แบบ Administrator แล้วลองใหม่
    exit /b %RC%
)

echo [WG] ติดตั้ง WireGuard for Windows สำเร็จ ✓
echo [WG] ต่อไป: ตั้ง "use_host_vpn": 1 ใน configmain.json แล้วรัน host-wg-rotate.bat
exit /b 0
