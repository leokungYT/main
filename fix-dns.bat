@echo off
chcp 65001 >nul
title Fix DNS
echo คืนค่า DNS ของทุกการ์ดเน็ตเป็นอัตโนมัติ (แก้ getaddrinfo failed / เข้าเว็บไม่ได้หลังปิด WARP/Surfshark)
echo ต้องรันแบบ Run as administrator
powershell -NoProfile -Command "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses -ErrorAction SilentlyContinue; Write-Host ('  reset DNS: ' + $_.Name) }"
ipconfig /flushdns
echo.
echo ทดสอบ:
nslookup assets.windscribe.com
pause
