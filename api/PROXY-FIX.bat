@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   PROXY-FIX for MuMu + mitmproxy
echo ============================================================
echo.

REM --- 1. find PC IP ---
set "PCIP="
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /C:"IPv4"') do (
    set "IP=%%A"
    set "IP=!IP: =!"
    echo !IP! | findstr /B "192.168." >nul && if "!PCIP!"=="" set "PCIP=!IP!"
    echo !IP! | findstr /B "10." >nul      && if "!PCIP!"=="" set "PCIP=!IP!"
    echo !IP! | findstr /B "172." >nul     && if "!PCIP!"=="" set "PCIP=!IP!"
)

if "%PCIP%"=="" (
    echo [ERROR] cannot find a LAN IP ^(192.168.* / 10.* / 172.*^)
    echo         run ipconfig manually and set it below
    pause
    exit /b 1
)

echo [1] PC IP detected: %PCIP%
echo.

REM --- 2. open firewall port 8888 ---
echo [2] opening Windows firewall port 8888 ...
netsh advfirewall firewall delete rule name="mitmproxy-8888" >nul 2>&1
netsh advfirewall firewall add rule name="mitmproxy-8888" dir=in action=allow protocol=TCP localport=8888 >nul
echo     done.
echo.

REM --- 3. reconnect adb ---
echo [3] reconnect adb ...
adb connect 127.0.0.1:7555 >nul
adb -s 127.0.0.1:7555 wait-for-device
echo     ok.
echo.

REM --- 4. set proxy ---
echo [4] set MuMu proxy to %PCIP%:8888 ...
adb -s 127.0.0.1:7555 shell settings put global http_proxy  %PCIP%:8888
adb -s 127.0.0.1:7555 shell settings put global https_proxy %PCIP%:8888
echo     done.
echo.

REM --- 5. verify ---
echo [5] verify proxy setting:
adb -s 127.0.0.1:7555 shell settings get global http_proxy
echo.

REM --- 6. open Wi-Fi settings as fallback in case global proxy is ignored ---
echo [6] opening Wi-Fi settings in MuMu as fallback ...
echo     if traffic still does not flow:
echo        - long-press Wi-Fi name in MuMu
echo        - Modify ^> Advanced ^> Proxy = Manual
echo        - Hostname = %PCIP%   Port = 8888
echo.
adb -s 127.0.0.1:7555 shell am start -a android.settings.WIFI_SETTINGS >nul 2>&1

echo ============================================================
echo   DONE. now:
echo     - open LGR in MuMu
echo     - watch flows at  http://127.0.0.1:8081
echo     - should see host  lrg.axelth.com
echo ============================================================
pause
