@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   YIGHT - drop .xml in input-id\, run this, done.
echo           decrypt + login + gift collect (no args needed)
echo ============================================================
echo.

rem --- load AES key ---
if "%LGR_AES_KEY%"=="" (
    if exist "key.txt" (
        set /p LGR_AES_KEY=<key.txt
        set "LGR_AES_KEY=!LGR_AES_KEY: =!"
    )
)
if "%LGR_AES_KEY%"=="" (
    echo [!] no AES key
    echo.
    echo    pick one:
    echo      [1] create key.txt next to this .bat with hex key inside
    echo          c:\Users\Administrator\Downloads\LGR\key.txt
    echo      [2] or: set LGR_AES_KEY=^<hex^>  before running
    echo.
    pause
    endlocal
    exit /b 1
)
echo [*] key    = %LGR_AES_KEY:~0,8%...%LGR_AES_KEY:~-8%

rem --- check folder ---
if not exist "input-id\" (
    mkdir "input-id"
    echo [*] created input-id\ - drop .xml files there first
    pause
    endlocal
    exit /b 0
)

rem --- count files ---
set "COUNT=0"
for %%f in (input-id\*.xml) do set /a COUNT+=1
if "%COUNT%"=="0" (
    echo [!] no .xml files in input-id\
    echo     put account .xml files there first
    pause
    endlocal
    exit /b 0
)
echo [*] folder = input-id\  (%COUNT% files)

echo.
echo [*] firing ...
echo.
python -X utf8 api\xml_fire.py --xml-dir "input-id" --gift

echo.
echo ============================================================
echo   done
echo ============================================================
pause
endlocal
