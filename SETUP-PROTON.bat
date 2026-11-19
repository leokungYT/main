@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   SETUP PROTON - ติดตั้ง ProtonVPN WG อัตโนมัติ
echo ============================================================
echo.

rem --- ถ้าลากโฟลเดอร์มาวางที่ไฟล์นี้ ใช้เลย ---
if not "%~1"=="" (
    if exist "%~1" (
        echo [*] ใช้ path ที่ลากมา: %~1
        set "SRC=%~1"
        goto :run
    )
)

rem --- auto-search: หาโฟลเดอร์ที่มี .conf แบบ Proton (ไม่มี PresharedKey) ---
echo [*] auto-search Proton .conf ใน:
echo     - โฟลเดอร์ปัจจุบัน + proton-configs\
echo     - %USERPROFILE%\Downloads
echo     - %USERPROFILE%\Desktop
echo.

set "FOUND="
for %%D in (
    "%~dp0proton-configs"
    "%~dp0"
    "%USERPROFILE%\Downloads\proton-configs"
    "%USERPROFILE%\Downloads"
    "%USERPROFILE%\Desktop\proton-configs"
    "%USERPROFILE%\Desktop"
) do (
    if exist "%%~D" (
        rem เช็กว่ามี .conf ขึ้นต้น proton- หรือเปล่า
        for %%F in ("%%~D\proton-*.conf") do (
            if exist "%%~F" (
                if not defined FOUND (
                    set "FOUND=%%~D"
                    echo [OK] เจอ Proton .conf ใน: %%~D
                )
            )
        )
    )
)

if not defined FOUND (
    echo [!] ไม่เจอ proton-*.conf ที่ไหนเลย
    echo.
    echo วิธีใช้:
    echo   1. โหลด Proton WG .conf 15 ไฟล์จาก account.proton.me/vpn/WireGuard
    echo   2. ลากโฟลเดอร์ที่เก็บ .conf มาวางที่ไฟล์ SETUP-PROTON.bat นี้
    echo      หรือ เอา .conf ไปไว้ที่ Downloads\proton-configs\
    echo      แล้วรันไฟล์นี้อีกครั้ง
    echo.
    pause
    exit /b 1
)
set "SRC=%FOUND%"

:run
echo.
echo ============================================================
echo [*] install-proton-wg.py "%SRC%"
echo ============================================================
echo.
python install-proton-wg.py "%SRC%"
if errorlevel 1 (
    echo.
    echo [!] install ล้มเหลว
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] เสร็จแล้ว - บอทจะ auto-detect Proton mode เอง
echo ============================================================
echo.
echo ขั้นต่อไป:
echo   1. ปิดบอทที่รันอยู่ (ถ้ามี)
echo   2. รัน autoupdate-lg.bat หรือ python login.py
echo   3. ควรเห็น log: [CONFIG] auto-detect Proton mode จาก wg/ip-chan/main-1 - override: ...
echo.
pause
endlocal
