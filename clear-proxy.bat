@echo off
REM Clear the proxy left on every connected emulator (fixes Authentication failed caused by a dead proxy)
cd /d "%~dp0"
for /f "skip=1 tokens=1" %%d in ('adb\adb.exe devices') do (
    echo Clearing proxy: %%d
    adb\adb.exe -s %%d shell settings put global http_proxy :0
    adb\adb.exe -s %%d shell settings delete global http_proxy
    adb\adb.exe -s %%d shell settings delete global global_http_proxy_host
    adb\adb.exe -s %%d shell settings delete global global_http_proxy_port
)
echo Done.
pause
