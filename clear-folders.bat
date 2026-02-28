@echo off
title Clear Backup Folders
cd /d "%~dp0"

echo =========================================
echo       CLEARING BACKUP FOLDERS...
echo =========================================
echo.

set FOLDERS=backup backup-id login-failed login-success not-found

for %%F in (%FOLDERS%) do (
    if exist "%%F" (
        rd /s /q "%%F"
        md "%%F"
        echo  [OK] Cleared folder: %%F
    ) else (
        md "%%F"
        echo  [OK] Created folder: %%F
    )
)

echo.
echo =========================================
echo   All folders have been cleared successfully!
echo =========================================
pause
