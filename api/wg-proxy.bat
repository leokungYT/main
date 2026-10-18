@echo off
rem เปิด wireproxy (WireGuard -> SOCKS5 127.0.0.1:1080) ให้สคริปต์ API ออกเน็ตผ่าน WG
rem + TCP tunnel 127.0.0.1:9443 -> rangers-api:443 (ให้ capture_team.py ส่งต่อผ่าน WG)
rem ใช้: wg-proxy.bat [ไฟล์ conf ใน ..\wg]   (ไม่ใส่ = New Jersey)
cd /d "%~dp0tools"
set CONF=%~1
if "%CONF%"=="" set CONF=Windscribe-New-Jersey-Situation-WG.conf
(type "..\..\wg\%CONF%" & echo. & echo [Socks5] & echo BindAddress = 127.0.0.1:1080 & echo. & echo [TCPClientTunnel] & echo BindAddress = 127.0.0.1:9443 & echo Target = rangers-api.line-apps.com:443) > wireproxy.conf
echo [*] WG proxy: %CONF%  -^>  socks5://127.0.0.1:1080
wireproxy.exe -s -c wireproxy.conf
