@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Double-click to run. Auto-detects ALL connected devices, captures each,
REM force-stops the game to lock the credential, saves to creds.json.
REM Optional: capture-auto.bat --use-login   (let login.py tap through PLAY)
python capture_auto.py %*
echo.
echo ===== DONE. Next: python test_login.py  /  python collect_all.py =====
pause
