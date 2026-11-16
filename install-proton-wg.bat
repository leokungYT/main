@echo off
REM install-proton-wg.bat - setup ProtonVPN per-emulator WG mode
REM usage: install-proton-wg.bat <path-to-proton-configs-folder>

cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo Usage: install-proton-wg.bat ^<path-to-proton-configs-folder^>
    echo.
    echo How to get Proton configs:
    echo   1. Sign up ProtonVPN Plus at https://protonvpn.com
    echo   2. Login at https://account.proton.me/vpn/WireGuard
    echo   3. Click "Create" to generate 15 WG configs (any country, NOT TH)
    echo      - Server: pick different servers for each (variety)
    echo      - NAT type: Moderate NAT
    echo      - VPN Accelerator: ON
    echo   4. Save all .conf files into ONE folder (e.g. Desktop\proton-configs\)
    echo   5. Run: install-proton-wg.bat C:\Users\t\Desktop\proton-configs
    echo.
    pause
    exit /b 1
)

python install-proton-wg.py "%~1"
pause
