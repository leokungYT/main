@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   UPDATE - download latest code from GitHub (NO git needed)
echo ============================================================
echo.

rem --- kill running bots first ---
echo [1/4] killing running bots...
taskkill /IM python.exe /F >nul 2>&1
taskkill /IM pythonw.exe /F >nul 2>&1
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

rem Python code
copy /y "%SRC%\login.py"              "%~dp0" >nul
copy /y "%SRC%\ranger-gear.py"        "%~dp0" >nul
copy /y "%SRC%\rangerplus.py"         "%~dp0" >nul 2>&1
copy /y "%SRC%\install-proton-wg.py"  "%~dp0" >nul
copy /y "%SRC%\patch-proton-config.py" "%~dp0" >nul
copy /y "%SRC%\fix-stuck-emu.py"      "%~dp0" >nul
copy /y "%SRC%\host_wg_rotator.py"    "%~dp0" >nul 2>&1
copy /y "%SRC%\wg_gen.py"             "%~dp0" >nul 2>&1

rem Batch files
copy /y "%SRC%\GO-PROTON.bat"         "%~dp0" >nul
copy /y "%SRC%\SETUP-PROTON.bat"      "%~dp0" >nul
copy /y "%SRC%\UPDATE.bat"            "%~dp0" >nul

rem proton-configs folder
if exist "%SRC%\proton-configs" (
    if not exist "%~dp0proton-configs" mkdir "%~dp0proton-configs"
    xcopy /y /e /q "%SRC%\proton-configs\*" "%~dp0proton-configs\" >nul
)

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
