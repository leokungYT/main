@echo off
rem FIX-ALL.bat - one-click maintenance (deployed to each remote via main repo)
rem Runs by dashboard: stop swap_bot -> flush DNS -> autoupdate -> restart swap_bot + agent

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   FIX-ALL: latest code + fresh swap_bot + network reset
echo ============================================================

rem --- 1) stop swap_bot (keep ExpressVPN tunnel) ---
echo [1/5] stop swap_bot.py...
wmic process where "name='python.exe' or name='pythonw.exe'" get ProcessId,CommandLine 2>nul | find /I "swap_bot.py" >nul
if !errorlevel! equ 0 (
    for /f "tokens=1" %%P in ('wmic process where "name='python.exe' or name='pythonw.exe'" get CommandLine^,ProcessId ^| findstr /I "swap_bot.py"') do (
        taskkill /F /PID %%P >nul 2>&1
    )
    echo       stopped
) else (
    echo       not running
)

rem --- 2) flush DNS + reset to DHCP ---
echo [2/5] flush DNS + reset to DHCP...
ipconfig /flushdns >nul 2>&1
powershell -NoProfile -Command "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses -ErrorAction SilentlyContinue }" >nul 2>&1

rem --- 3) autoupdate-lg (pulls latest code from github) ---
echo [3/5] pull latest code via autoupdate-lg.bat...
if exist "autoupdate-lg.bat" (
    call autoupdate-lg.bat >nul 2>&1
    echo       update done
) else (
    echo       [SKIP] autoupdate-lg.bat not found
)

rem --- 4) restart swap_bot.py ---
echo [4/5] restart swap_bot.py...
if exist "%~dp0swap_bot\swap_bot.py" (
    start "" /D "%~dp0swap_bot" pythonw "%~dp0swap_bot\swap_bot.py"
    echo       swap_bot.py started
) else (
    echo       [SKIP] swap_bot\swap_bot.py not found
)

rem --- 5) restart agent.py if present ---
echo [5/5] restart agent.py (if present)...
if exist "%USERPROFILE%\Downloads\remote\remote-file\agent.py" (
    wmic process where "name='python.exe' or name='pythonw.exe'" get CommandLine 2>nul | find /I "agent.py" >nul
    if !errorlevel! neq 0 (
        start "" /D "%USERPROFILE%\Downloads\remote\remote-file" pythonw "%USERPROFILE%\Downloads\remote\remote-file\agent.py"
        echo       agent.py started
    ) else (
        echo       agent.py already running
    )
) else (
    echo       [SKIP] agent.py not installed
)

echo.
echo ============================================================
echo   FIX-ALL done - wait 30s then check dashboard
echo ============================================================

rem dashboard reads first line to report result
> "%~dp0autoupdate-lg.log" echo OK fix-all finished %date% %time%
exit /b 0
