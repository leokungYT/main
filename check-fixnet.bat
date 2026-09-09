@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Check fixnet (diagnose)
python check-fixnet.py %*
pause
