@echo off
REM Generate Windscribe WireGuard configs into wg\ (key pair from a .conf or wg\keypair.txt)
cd /d "%~dp0"
set /p N=How many screens on this PC? (default 15): 
if "%N%"=="" set N=15
set /p M=Machine number 1-30 (blank = single PC): 
if "%M%"=="" set M=0
python -c "import wg_gen; wg_gen.generate(int(%N%), None, 'wg', int(%M%))"
pause
