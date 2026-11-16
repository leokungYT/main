@echo off
REM headless Windscribe rotator - ฟัง .host_wg_trigger แล้วสั่ง windscribe-cli
REM ไม่ต้องให้หน้าต่าง Windscribe โผล่ ไม่ต้องขยับเมาส์
cd /d "%~dp0"
python windscribe_cli_rotator.py
pause
