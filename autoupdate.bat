@echo off
setlocal enabledelayedexpansion

:: =========================================================
:: Auto Update Script for Ranger Bot (Install to 'main' folder)
:: =========================================================
:: URL: https://github.com/leokungYT/main
:: =========================================================

echo.
echo ============================================
echo.

:: Kill ADB and Python processes to prevent file locks
echo [PRE] Stopping ADB and Bot processes...
taskkill /f /im adb.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

set "TARGET_FOLDER=main"
set "REPO_URL=https://github.com/leokungYT/main/archive/refs/heads/main.zip"
set "ZIP_NAME=main_update.zip"
set "EXTRACT_DIR=update_temp"

:: 1. Create target folder if it doesn't exist
if not exist "%TARGET_FOLDER%" (
    echo [INFO] Creating directory: %TARGET_FOLDER%
    mkdir "%TARGET_FOLDER%"
)

:: 2. Download the latest version
echo [1/4] Downloading latest version from GitHub...
curl -L %REPO_URL% -o %ZIP_NAME%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Download failed! Please check your internet connection.
    pause
    exit /b 1
)

:: 3. Extract files
echo [2/4] Extracting files...
if exist "%EXTRACT_DIR%" rd /s /q "%EXTRACT_DIR%"
powershell -Command "Expand-Archive -Path '%ZIP_NAME%' -DestinationPath '%EXTRACT_DIR%' -Force"

:: Identify the source directory (GitHub zips name files like 'main-main')
for /d %%f in ("%EXTRACT_DIR%\*") do set "SOURCE_FOLDER=%%f"

if not defined SOURCE_FOLDER (
    echo.
    echo [ERROR] Extraction failed! ZIP might be corrupt.
    pause
    exit /b 1
)

:: 4. Update files (Mirror/Overwrite into target 'main' folder)
echo [3/4] Updating files in %TARGET_FOLDER% folder...
:: /s /e /y /q: recursive, include empty folders, overwrite, quiet
xcopy /s /e /y /q "%SOURCE_FOLDER%\*" "%TARGET_FOLDER%\"

:: 5. Cleanup
echo [4/4] Cleaning up temporary files...
del /q "%ZIP_NAME%"
rd /s /q "%EXTRACT_DIR%"

echo.
echo ============================================
echo      Update Successful! (Saved in %TARGET_FOLDER%)
echo ============================================
echo.
pause
