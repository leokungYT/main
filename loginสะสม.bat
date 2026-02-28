@echo off
cd /d "%~dp0"
:: รันโปรแกรม python แยกหน้าต่างออกมา แล้วปิดหน้าต่าง .bat อันนี้ทิ้งไปเลย
start "" python login.py
