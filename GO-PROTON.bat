@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   GO-PROTON - full migration: kill bot + pull + install
echo ============================================================
echo.

rem --- Step 1: KILL all running bots (python.exe running login.py / ranger-gear.py) ---
echo [1/5] killing running bots (python + MuMu processes untouched)...
for /f "tokens=2" %%P in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr /b "PID:"') do (
    taskkill /PID %%P /F >nul 2>&1
)
rem also kill pythonw.exe (GUI bots)
for /f "tokens=2" %%P in ('tasklist /fi "imagename eq pythonw.exe" /fo list ^| findstr /b "PID:"') do (
    taskkill /PID %%P /F >nul 2>&1
)
echo       done
echo.

rem --- Step 2: git pull ---
echo [2/5] git pull...
git pull
if errorlevel 1 (
    echo [!] git pull failed - fix conflict then re-run
    pause
    exit /b 1
)
echo.

rem --- Step 3: verify version ---
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
    echo [!] no proton-configs folder with .conf files found
    echo     expected at: %~dp0proton-configs  (or Downloads\proton-configs)
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
echo   - verify log shows: [CONFIG] auto-detect Proton mode ...
echo.
pause
endlocal
exit /b 0
