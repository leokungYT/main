@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Extract ZIP to Backup
cd /d "%~dp0"

echo.
echo ============================================
echo   Extract ZIP files to backup folder
echo ============================================
echo.

:: Create folders if not exist
if not exist "zip-input" (
    mkdir "zip-input"
    echo [INFO] Created folder: zip-input
)
if not exist "backup" (
    mkdir "backup"
    echo [INFO] Created folder: backup
)

:: Count ZIP files
set ZIP_COUNT=0
for %%f in ("zip-input\*.zip") do set /a ZIP_COUNT+=1

if %ZIP_COUNT%==0 (
    echo [!] No ZIP files found in zip-input folder!
    echo.
    echo     Please put your .zip files in the "zip-input" folder
    echo     then run this script again.
    echo.
    pause
    exit /b
)

echo [OK] Found %ZIP_COUNT% ZIP file(s) in zip-input folder
echo.

:: Extract each ZIP to temp, move only .xml to backup
set "TEMP_DIR=_extract_temp"
set TOTAL_XML=0

for %%f in ("zip-input\*.zip") do (
    echo [EXTRACT] %%~nxf ...
    
    :: Clean temp
    if exist "%TEMP_DIR%" rd /s /q "%TEMP_DIR%"
    
    :: Extract to temp
    powershell -Command "Expand-Archive -Path '%%f' -DestinationPath '%TEMP_DIR%' -Force"
    
    :: Move all .xml files from temp (including subfolders) to backup
    set FILE_COUNT=0
    for /r "%TEMP_DIR%" %%x in (*.xml) do (
        move /y "%%x" "backup\" >nul 2>&1
        set /a FILE_COUNT+=1
        set /a TOTAL_XML+=1
    )
    
    echo          -> Moved !FILE_COUNT! XML file(s) to backup
)

:: Cleanup temp folder
if exist "%TEMP_DIR%" rd /s /q "%TEMP_DIR%"

echo.
echo ============================================
echo   Done! Processed %ZIP_COUNT% ZIP file(s)
echo   Total XML files moved to backup: %TOTAL_XML%
echo ============================================
echo.
pause
