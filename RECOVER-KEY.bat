@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   RECOVER-KEY - find AES key from existing creds.json + XML
echo                 known-plaintext attack, no frida/mumu needed
echo ============================================================
echo.

if not exist "creds.json" (
    echo [!] creds.json not found at repo root
    echo     this script needs decrypted guestCookie to reverse the key
    pause
    endlocal
    exit /b 1
)

python -X utf8 api\RECOVER-KEY.py

pause
endlocal
