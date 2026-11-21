@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   GEN-PROTON - one-click: auto-create + install ProtonVPN WG
echo ============================================================
echo.
echo สคริปต์นี้จะ:
echo   1. ตรวจ/ติดตั้ง playwright (เปิด Chromium)
echo   2. เปิดเบราว์เซอร์ให้คุณ login Proton ด้วยตัวเอง (ปลอดภัย)
echo   3. สร้าง Proton WG config อัตโนมัติตามจำนวนที่ระบุ
echo   4. ติดตั้งลงโฟลเดอร์ wg\ ให้บอตใช้ได้เลย
echo.
echo ============================================================
echo.

rem --- รับจำนวนจาก arg หรือถาม ---
set "COUNT=%~1"
if "%COUNT%"=="" (
    set /p COUNT="จำนวน config ที่ต้องการ (default 15): "
)
if "%COUNT%"=="" set "COUNT=15"

rem เช็คว่าเป็นตัวเลขหรือไม่ (ถ้าไม่ใช่ใช้ 15)
set /a CHECK=%COUNT% 2>nul
if "%CHECK%"=="0" set "COUNT=15"
if %CHECK% LSS 1 set "COUNT=15"
if %CHECK% GTR 200 (
    echo [!] %COUNT% เยอะเกินไป - จำกัดที่ 100
    set "COUNT=100"
)

set "OUTDIR=%~dp0proton-configs"

echo [*] จะสร้าง %COUNT% configs ไปที่: %OUTDIR%
echo.

rem --- ตรวจว่ามี playwright ติดตั้งแล้วหรือยัง ---
python -c "import playwright" 2>nul
if errorlevel 1 (
    echo [*] ยังไม่มี playwright - กำลังติดตั้ง...
    python -m pip install playwright
    if errorlevel 1 (
        echo [!] pip install ล้มเหลว - เช็ค Python/network แล้วลองใหม่
        pause
        exit /b 1
    )
    echo [*] ติดตั้ง Chromium (ประมาณ 170MB - ครั้งแรกใช้เวลาสักพัก)...
    python -m playwright install chromium
    if errorlevel 1 (
        echo [!] playwright install chromium ล้มเหลว
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo [*] เริ่มสร้าง Proton configs...
echo     - จะเปิดเบราว์เซอร์ให้ login เอง
echo     - หลัง login เสร็จกลับมากด Enter ใน terminal นี้
echo ============================================================
echo.

python auto-create-proton-configs.py --count %COUNT% --out "%OUTDIR%"
if errorlevel 1 (
    echo.
    echo [!] auto-create ล้มเหลว - ดู error ด้านบน
    pause
    exit /b 1
)

rem --- นับไฟล์ที่ได้มา ---
set "GOT=0"
for %%F in ("%OUTDIR%\*.conf") do set /a GOT+=1
echo.
echo [*] สร้างได้ %GOT% ไฟล์ใน %OUTDIR%

if %GOT% EQU 0 (
    echo [!] ไม่มีไฟล์ .conf สร้างออกมา - ตรวจเบราว์เซอร์/ login
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [*] ติดตั้งลง wg\ ให้บอตใช้งาน...
echo ============================================================
echo.

python install-proton-wg.py "%OUTDIR%"
if errorlevel 1 (
    echo.
    echo [!] install ล้มเหลว - ลองรัน install-proton-wg.py "%OUTDIR%" เองดู
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] เสร็จแล้ว - %GOT% Proton configs พร้อมใช้
echo ============================================================
echo.
echo ขั้นตอนถัดไป:
echo   1. ปิดบอตที่กำลังรันอยู่ (ถ้ามี)
echo   2. รัน autoupdate-lg.bat หรือ python login.py
echo   3. ควรเห็น: [CONFIG] FORCE Proton mode ...
echo.
pause
endlocal
exit /b 0
