@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   COLLECT CREDS - XML -^> decrypt -^> login -^> creds.json
echo ============================================================
echo.

if "%LGR_AES_KEY%"=="" (
    echo [!] env LGR_AES_KEY not set
    echo     set LGR_AES_KEY=^<hex 32 or 64^>
    echo     แล้วรันใหม่
    pause
    endlocal
    exit /b 1
)
echo [*] key    = %LGR_AES_KEY:~0,8%...%LGR_AES_KEY:~-8%
echo [*] creds  = creds.json

if "%1"=="" (
    echo [*] usage:
    echo     COLLECT-CREDS.bat ^<xml-dir^>            รัน folder
    echo     COLLECT-CREDS.bat ^<xml-dir^> --gift     เก็บ gift ด้วย
    echo     COLLECT-CREDS.bat ^<xml-dir^> --force    เขียนทับของเก่า
    echo.
    pause
    endlocal
    exit /b 1
)

python -X utf8 collect_creds.py --xml-dir "%1" %2 %3 %4 %5

pause
endlocal
