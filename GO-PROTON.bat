@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   GO-PROTON - full migration: kill bot + pull + install
echo ============================================================
echo.

rem --- Step 1: KILL running bots (simple, no for-loop to avoid "Out of memory") ---
echo [1/5] killing running bots...
taskkill /IM python.exe /F >nul 2>&1
taskkill /IM pythonw.exe /F >nul 2>&1
echo       done
echo.

rem --- Step 2: find git executable ---
echo [2/5] finding git...
set "GIT="
where git >nul 2>&1
if not errorlevel 1 (
    set "GIT=git"
    goto git_found
)
rem common install locations
for %%G in (
    "C:\Program Files\Git\bin\git.exe"
    "C:\Program Files (x86)\Git\bin\git.exe"
    "%LOCALAPPDATA%\Programs\Git\bin\git.exe"
    "%USERPROFILE%\scoop\apps\git\current\bin\git.exe"
    "C:\msys64\usr\bin\git.exe"
) do (
    if exist "%%~G" (
        set "GIT=%%~G"
        goto git_found
    )
)
rem GitHub Desktop portable git (version-dir varies)
for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
    if exist "%%~D\resources\app\git\cmd\git.exe" (
        set "GIT=%%~D\resources\app\git\cmd\git.exe"
        goto git_found
    )
)

echo [!] git.exe NOT FOUND on this PC
echo     install: https://git-scm.com/download/win
echo     or run: winget install Git.Git
pause
exit /b 1

:git_found
echo       using git: !GIT!
echo.

rem --- Step 3: git pull ---
echo [3/5] git pull...
"!GIT!" pull
if errorlevel 1 (
    echo [!] git pull failed - fix conflict then re-run
    pause
    exit /b 1
)
echo.

rem --- Step 4: show version + find proton configs ---
echo [4/5] bot version:
findstr /c:"BOT_VERSION =" login.py
echo.
echo       finding Proton .conf...
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
    echo     expected at: %~dp0proton-configs
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
