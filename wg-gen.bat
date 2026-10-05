@echo off
REM Generate Windscribe WireGuard configs into wg\ (uses the key pair from a .conf already in wg\)
cd /d "%~dp0"
set /p N=How many screens? (default 30): 
if "%N%"=="" set N=30
python wg_gen.py %N%
pause
