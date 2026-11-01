@echo off
REM Generate Windscribe WireGuard configs
REM - ไม่ระบุ wg_profile ใน configmain.json -> ลง wg\
REM - ระบุ wg_profile (string / list) -> ลงทุกโฟลเดอร์ย่อยที่ตั้งไว้
cd /d "%~dp0"
set /p N=How many screens on this PC? (default 15):
if "%N%"=="" set N=15
set /p M=Machine number 1-30 (blank = single PC):
if "%M%"=="" set M=0
python wg_gen.py %N% --machine %M%
pause
