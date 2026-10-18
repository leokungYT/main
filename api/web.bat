@echo off
rem เปิดเว็บ (เปิด WG proxy ให้เองในตัว ไม่ต้องเปิด wg-proxy.bat)
cd /d "%~dp0"
python web_app.py %*
