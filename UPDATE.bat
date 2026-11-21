@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   UPDATE - download latest code from GitHub (NO git needed)
echo ============================================================
echo.

rem --- kill running bots first (PowerShell - no taskkill hang) ---
echo [1/4] killing running bots...
powershell -NoProfile -Command "Get-Process -Name python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
echo       done
echo.

rem --- download main.zip from GitHub via PowerShell ---
echo [2/4] downloading latest main.zip from GitHub...
set "URL=https://github.com/leokungYT/main/archive/refs/heads/main.zip"
set "ZIP=%TEMP%\lgr-main.zip"
set "EXTRACT=%TEMP%\lgr-main-extract"

if exist "%ZIP%" del /q "%ZIP%" >nul 2>&1
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%" >nul 2>&1

powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] download failed - check internet connection
    pause
    exit /b 1
)
echo       downloaded to %ZIP%
echo.

rem --- extract zip ---
echo [3/4] extracting...
powershell -NoProfile -Command "try { Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] extract failed
    pause
    exit /b 1
)
echo       extracted to %EXTRACT%\main-main\
echo.

rem --- copy updated files (NOT configmain.json/creds.json/wg/) ---
echo [4/4] copying updated files...
set "SRC=%EXTRACT%\main-main"
if not exist "%SRC%\login.py" (
    echo [!] extracted content missing - %SRC%\login.py not found
    pause
    exit /b 1
)

rem === sync EVERYTHING from GitHub zip, except user data ===
rem exclude list (xcopy /exclude takes a file with one pattern per line, substring match)
set "EXCLUDE=%TEMP%\lgr_update_exclude.txt"
> "%EXCLUDE%" (
    echo \backup\
    echo \backup-id\
    echo \backup-xml\
    echo \backup-fail\
    echo \input-id\
    echo \login-success\
    echo \login-failed\
    echo \login-fail\
    echo \random-fail\
    echo \play-stage30-100-150\
    echo \ranger-locks\
    echo \7day-check\
    echo \wg\
    echo \api\
    echo \.git\
    echo configmain.json
    echo evpn_creds.txt
    echo creds.json
    echo .evpn_creds
    echo shared_stats.json
)

xcopy /y /e /q /exclude:"%EXCLUDE%" "%SRC%\*" "%~dp0" >nul
del /q "%EXCLUDE%" >nul 2>&1

rem cleanup
del /q "%ZIP%" >nul 2>&1
rmdir /s /q "%EXTRACT%" >nul 2>&1

echo       files copied OK
echo.
echo ============================================================
echo [DONE] code updated to latest GitHub main
echo ============================================================
echo.
echo       bot version:
findstr /c:"BOT_VERSION =" login.py
echo.
echo NEXT:
echo   - run: GO-PROTON.bat         (one-click install Proton)
echo   - or run: SETUP-PROTON.bat    (just install Proton configs)
echo   - then launch bot as usual
echo.
pause
endlocal
exit /b 0
