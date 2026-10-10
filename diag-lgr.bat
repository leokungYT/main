@echo off
chcp 65001 >nul
title LGR diag
cd /d "%~dp0"
echo ตรวจเครื่องบอท (อ่านอย่างเดียว ไม่แก้อะไร) - ใช้เวลาประมาณ 1-3 นาที
python diag_lgr.py
pause
