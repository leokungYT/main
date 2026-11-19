@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   DIRECT - xml -^> decrypt -^> login -^> gift -^> print
echo            ไม่แตะ MuMu, ไม่เก็บ creds.json, จบในรันเดียว
echo ============================================================
echo.

if "%LGR_AES_KEY%"=="" (
    echo [!] env LGR_AES_KEY not set
    echo     set LGR_AES_KEY=^<hex 32 or 64^>
    pause
    endlocal
    exit /b 1
)
echo [*] key = %LGR_AES_KEY:~0,8%...%LGR_AES_KEY:~-8%

if "%1"=="" (
    echo.
    echo usage:
    echo   DIRECT.bat ^<file.xml^>                     ไฟล์เดียว, แค่ login+home
    echo   DIRECT.bat ^<file.xml^> --gift              เก็บ gift ด้วย
    echo   DIRECT.bat ^<folder^>                       ทั้ง folder
    echo   DIRECT.bat ^<folder^> --gift --limit 20     20 ไฟล์แรก, เก็บ gift
    echo   DIRECT.bat ^<file.xml^> --dump              พิมพ์ req/res ดิบ
    echo.
    pause
    endlocal
    exit /b 1
)

if exist "%~1\*" (
    python -X utf8 xml_fire.py --xml-dir "%~1" %2 %3 %4 %5 %6 %7 %8 %9
) else (
    python -X utf8 xml_fire.py --xml "%~1" %2 %3 %4 %5 %6 %7 %8 %9
)

pause
endlocal
