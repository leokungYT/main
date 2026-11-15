@echo off
REM windscribe-gui-rotate.bat - automate Windscribe desktop app GUI
REM listens for bot's fixnet1 trigger -> clicks random country in Windscribe

cd /d "%~dp0"

echo [WS-GUI] Installing required python modules (pyautogui pygetwindow)...
python -m pip install pyautogui pygetwindow pillow -q 2>nul

echo.
echo [WS-GUI] Starting rotator...
echo   - Keep Windscribe desktop app window visible
echo   - Move mouse to top-left corner to emergency-stop the rotator
echo.
python windscribe_gui_rotator.py %*
pause
