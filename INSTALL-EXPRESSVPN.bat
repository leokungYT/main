@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   INSTALL-EXPRESSVPN - download + install ExpressVPN (Windows)
echo ============================================================
echo.

rem --- ตรวจว่าติดตั้งอยู่แล้วหรือยัง ---
set "EVPN_EXE="
if exist "C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
if "%EVPN_EXE%"=="" if exist "C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe" set "EVPN_EXE=C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"

if not "%EVPN_EXE%"=="" (
    echo [OK] ExpressVPN ติดตั้งอยู่แล้ว: %EVPN_EXE%
    goto show_creds
)

echo [*] ยังไม่พบ ExpressVPN - กำลังโหลด installer...
echo.

set "INSTALLER=%TEMP%\expressvpn_installer.exe"
set "URL=https://www.expressvpn.com/clients/latest/windows"

powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%URL%' -OutFile '%INSTALLER%' -UseBasicParsing -MaximumRedirection 10; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] โหลด installer ไม่สำเร็จ - โหลดเองจาก:
    echo     %URL%
    pause
    exit /b 1
)

echo [*] โหลดเสร็จ: %INSTALLER%
echo.
echo [*] เปิด installer (ต้องกด UAC = Yes)...
echo     - ติดตั้งแบบ default เลย ไม่ต้องเปลี่ยนอะไร
echo     - เสร็จแล้วจะเปิด ExpressVPN ให้ login
start "" "%INSTALLER%"

echo.
echo [*] รอให้ติดตั้งเสร็จ... (กด Enter เมื่อหน้าต่าง "Sign In" ของ ExpressVPN ขึ้นมาแล้ว)
pause >nul

:show_creds
echo.
echo ============================================================
echo [STEP 1] login ExpressVPN ด้วยบัญชีนี้ (copy-paste):
echo ============================================================
if exist evpn_creds.txt (
    type evpn_creds.txt
) else (
    echo [!] evpn_creds.txt ไม่พบ - ใส่ email/password เองตามปกติ
)
echo.
echo ============================================================
echo [STEP 2] หลัง login สำเร็จแล้ว ต่อ VPN ให้เรียบร้อย (ประเทศไหนก็ได้)
echo ============================================================
echo.
echo [*] เสร็จแล้วปิดหน้าต่างนี้ - ครั้งถัดไป loginสะสม.bat จะเปิด ExpressVPN + swap_bot ให้เอง
echo.
pause
endlocal
exit /b 0
