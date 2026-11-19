@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   GO-PROTON - full migration: kill bot + update + install
echo ============================================================
echo.

rem --- Step 1: KILL running bots (PowerShell - no taskkill hang) ---
echo [1/5] killing running bots...
powershell -NoProfile -Command "Get-Process -Name python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
echo       done
echo.

rem --- Step 2: find git or fallback to PowerShell zip download ---
echo [2/5] updating code...
set "GIT="
where git >nul 2>&1
if not errorlevel 1 (
    set "GIT=git"
    goto git_found
)
for %%G in (
    "C:\Program Files\Git\bin\git.exe"
    "C:\Program Files (x86)\Git\bin\git.exe"
    "%LOCALAPPDATA%\Programs\Git\bin\git.exe"
    "%USERPROFILE%\scoop\apps\git\current\bin\git.exe"
) do (
    if exist "%%~G" (
        set "GIT=%%~G"
        goto git_found
    )
)
for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
    if exist "%%~D\resources\app\git\cmd\git.exe" (
        set "GIT=%%~D\resources\app\git\cmd\git.exe"
        goto git_found
    )
)

rem --- no git found -> use PowerShell zip download ---
echo       no git found - using PowerShell zip download fallback
set "URL=https://github.com/leokungYT/main/archive/refs/heads/main.zip"
set "ZIP=%TEMP%\lgr-main.zip"
set "EXTRACT=%TEMP%\lgr-main-extract"

if exist "%ZIP%" del /q "%ZIP%" >nul 2>&1
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%" >nul 2>&1

powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] download failed - check internet
    pause
    exit /b 1
)
powershell -NoProfile -Command "try { Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACT%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo [!] extract failed
    pause
    exit /b 1
)
set "SRC=%EXTRACT%\main-main"
if not exist "%SRC%\login.py" (
    echo [!] extracted content missing
    pause
    exit /b 1
)
rem copy updated files (NOT configmain.json/creds.json/wg/)
copy /y "%SRC%\login.py"               "%~dp0" >nul
copy /y "%SRC%\ranger-gear.py"         "%~dp0" >nul
copy /y "%SRC%\rangerplus.py"          "%~dp0" >nul 2>&1
copy /y "%SRC%\install-proton-wg.py"   "%~dp0" >nul
copy /y "%SRC%\patch-proton-config.py" "%~dp0" >nul
copy /y "%SRC%\fix-stuck-emu.py"       "%~dp0" >nul
copy /y "%SRC%\host_wg_rotator.py"     "%~dp0" >nul 2>&1
copy /y "%SRC%\wg_gen.py"              "%~dp0" >nul 2>&1
copy /y "%SRC%\GO-PROTON.bat"          "%~dp0" >nul
copy /y "%SRC%\SETUP-PROTON.bat"       "%~dp0" >nul
copy /y "%SRC%\UPDATE.bat"             "%~dp0" >nul
if exist "%SRC%\proton-configs" (
    if not exist "%~dp0proton-configs" mkdir "%~dp0proton-configs"
    xcopy /y /e /q "%SRC%\proton-configs\*" "%~dp0proton-configs\" >nul
)
del /q "%ZIP%" >nul 2>&1
rmdir /s /q "%EXTRACT%" >nul 2>&1
echo       code updated via PowerShell zip
goto after_update

:git_found
echo       using git: !GIT!
"!GIT!" pull
if errorlevel 1 (
    echo [!] git pull failed
    pause
    exit /b 1
)

:after_update
echo.

rem --- Step 3: show version ---
echo [3/5] bot version:
findstr /c:"BOT_VERSION =" login.py
echo.

rem --- Step 4: find proton configs ---
echo [4/5] finding Proton .conf...
set "SRC="
if exist "%~dp0proton-configs" (
    for %%F in ("%~dp0proton-configs\*.conf") do (
        if exist "%%~F" (
            if not defined SRC set "SRC=%~dp0proton-configs"
        )
    )
)
if not defined SRC (
    for %%F in ("%USERPROFILE%\Downloads\proton-configs\*.conf") do (
        if exist "%%~F" (
            if not defined SRC set "SRC=%USERPROFILE%\Downloads\proton-configs"
        )
    )
)
if not defined SRC (
    echo [!] no proton-configs folder found
    pause
    exit /b 1
)
echo       using: !SRC!
echo.

rem --- Step 5: install ---
echo [5/5] installing Proton configs...
python install-proton-wg.py "!SRC!"
if errorlevel 1 (
    echo [!] install failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] all set - bot killed, code updated, Proton installed
echo ============================================================
echo.
echo NEXT:
echo   - double-click your usual launcher (autoupdate-lg.bat / GUI)
echo   - or run: python login.py
echo   - verify log shows: [CONFIG] FORCE Proton mode - override: ...
echo.
pause
endlocal
exit /b 0
