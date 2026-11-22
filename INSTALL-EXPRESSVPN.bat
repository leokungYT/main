@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   INSTALL-EXPRESSVPN - browser-assisted install
echo ============================================================
echo.

rem --- 1) check if already installed ---
set "EVPN_EXE="
set "P1=C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P2=C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
set "P3=C:\Program Files (x86)\ExpressVPN\ExpressVPN.exe"
set "P4=C:\Program Files\ExpressVPN\ExpressVPN.exe"
if exist "!P1!" set "EVPN_EXE=!P1!"
if "!EVPN_EXE!"=="" if exist "!P2!" set "EVPN_EXE=!P2!"
if "!EVPN_EXE!"=="" if exist "!P3!" set "EVPN_EXE=!P3!"
if "!EVPN_EXE!"=="" if exist "!P4!" set "EVPN_EXE=!P4!"

if not "!EVPN_EXE!"=="" (
    echo [OK] ExpressVPN already installed: !EVPN_EXE!
    echo.
    goto launch_and_login
)

rem --- 2) open download page in default browser (user signs in and gets installer) ---
echo [1/3] Opening ExpressVPN download page in your browser...
echo       - Sign in with your account (creds below)
echo       - Click "Download for Windows"
echo       - Run the downloaded installer (default settings, click Next)
echo       - Come BACK here when install is complete
echo.

if exist evpn_creds.txt (
    echo ============================================================
    echo [SIGN-IN CREDENTIALS]
    echo ============================================================
    type evpn_creds.txt
    echo ============================================================
    echo.
)

start "" "https://www.expressvpn.com/latest#windows"
echo.
echo       Press Enter here AFTER you installed ExpressVPN...
pause >nul

rem --- 3) wait for exe to appear ---
echo [2/3] Checking for ExpressVPN.exe...
for /l %%i in (1,1,30) do (
    if exist "!P1!" set "EVPN_EXE=!P1!" & goto found_exe
    if exist "!P2!" set "EVPN_EXE=!P2!" & goto found_exe
    if exist "!P3!" set "EVPN_EXE=!P3!" & goto found_exe
    if exist "!P4!" set "EVPN_EXE=!P4!" & goto found_exe
    timeout /t 2 /nobreak >nul
)
echo [!] ExpressVPN.exe not found in any known path
echo     Check if install really finished then re-run this script
pause
exit /b 1

:found_exe
echo       found: !EVPN_EXE!
echo.

:launch_and_login
echo [3/3] Launching ExpressVPN + loading credentials into clipboard...

rem read email/password from local file
set "EMAIL="
set "PASSWORD="
if exist evpn_creds.txt (
    for /f "usebackq tokens=1,* delims==" %%a in ("evpn_creds.txt") do (
        if /i "%%a"=="email" set "EMAIL=%%b"
        if /i "%%a"=="password" set "PASSWORD=%%b"
    )
)

rem launch ExpressVPN if not already running
tasklist /FI "IMAGENAME eq ExpressVPN.exe" 2>nul | find /I "ExpressVPN.exe" >nul
if !errorlevel! equ 1 start "" "!EVPN_EXE!"

echo.
echo ============================================================
echo [STEP 1 of 2] EMAIL in clipboard
echo ============================================================
if not "!EMAIL!"=="" (
    echo !EMAIL!| clip
    echo   email: !EMAIL!
    echo   -^> In ExpressVPN: click email field, Ctrl+V
    echo.
    echo Press Enter AFTER pasting email...
    pause >nul

    echo.
    echo ============================================================
    echo [STEP 2 of 2] PASSWORD in clipboard
    echo ============================================================
    echo !PASSWORD!| clip
    echo   -^> In ExpressVPN: click password field, Ctrl+V, click "Sign In"
    echo.
    echo Press Enter AFTER you clicked Sign In...
    pause >nul
) else (
    echo [!] evpn_creds.txt not found - sign in manually
    pause
)

echo.
echo ============================================================
echo [DONE] next: double-click loginสะสม.bat
echo              auto-launches ExpressVPN + swap_bot + python login.py
echo ============================================================
echo.
pause
endlocal
exit /b 0
