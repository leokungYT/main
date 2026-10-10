@echo off
chcp 65001 >nul
setlocal
title Test old version (ed72110)

:: =========================================================
:: ทดสอบโค้ดเวอร์ชันก่อนวันที่ 8 (commit ed72110) แยกโฟลเดอร์ ไม่ทับของเดิม
:: วางไฟล์นี้ไว้ในโฟลเดอร์ main แล้วดับเบิลคลิก
:: จะสร้าง ..\main-old (ข้าง main) + ก๊อป config / wg / wg_accounts / input-id ไปให้ แล้วเปิดบอท
:: =========================================================

set "SRC=%~dp0"
set "OLD=%~dp0..\main-old"
set "ZIP=%TEMP%\lgr_ed72110.zip"
set "TMPX=%TEMP%\lgr_ed72110"

echo [1/4] ปิดบอทตัวที่รันอยู่ (python / adb)...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im adb.exe >nul 2>&1
timeout /t 2 /nobreak >nul

if exist "%OLD%\login.py" (
    echo [2/4] มี main-old อยู่แล้ว - ใช้ตัวเดิม ไม่โหลดซ้ำ
    goto copydata
)

echo [2/4] โหลดโค้ดเวอร์ชันเก่า ed72110 จาก GitHub...
curl -k -L --retry 3 --connect-timeout 15 "https://github.com/leokungYT/main/archive/ed72110.zip" -o "%ZIP%"
if errorlevel 1 (
    echo [ERROR] โหลดไม่สำเร็จ - เช็คเน็ตแล้วลองใหม่
    pause
    exit /b 1
)
if exist "%TMPX%" rd /s /q "%TMPX%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TMPX%' -Force"
for /d %%f in ("%TMPX%\*") do set "UNZ=%%f"
if not defined UNZ (
    echo [ERROR] แตกไฟล์ไม่สำเร็จ
    pause
    exit /b 1
)
robocopy "%UNZ%" "%OLD%" /E /NJH /NJS /NP /NFL /NDL >nul
rd /s /q "%TMPX%"
del /q "%ZIP%"

:copydata
echo [3/4] ก๊อป config / wg / wg_accounts / input-id จาก main ไป main-old...
copy /y "%SRC%configmain.json" "%OLD%\configmain.json" >nul
if exist "%SRC%ranger-gear_config.json" copy /y "%SRC%ranger-gear_config.json" "%OLD%\ranger-gear_config.json" >nul
if exist "%SRC%wg" robocopy "%SRC%wg" "%OLD%\wg" /E /NJH /NJS /NP /NFL /NDL >nul
if exist "%SRC%wg_accounts" robocopy "%SRC%wg_accounts" "%OLD%\wg_accounts" /E /NJH /NJS /NP /NFL /NDL >nul
if exist "%SRC%input-id" robocopy "%SRC%input-id" "%OLD%\input-id" /E /NJH /NJS /NP /NFL /NDL >nul

echo [4/4] เปิดบอทเวอร์ชันเก่า...
echo ============================================
echo  กำลังรัน: %OLD%\login.py  (เวอร์ชัน ed72110)
echo  ปล่อยรัน 30-60 นาที แล้วดูว่ายัง timeout / offline / fixid ไหม
echo  เสร็จแล้วปิดหน้าต่างนี้ กลับไปใช้ main ตามปกติได้เลย
echo ============================================
cd /d "%OLD%"
python login.py
pause
