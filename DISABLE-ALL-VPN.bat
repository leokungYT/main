@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   DISABLE-ALL-VPN - ปิด VPN ทุกรูปแบบ (one-click)
echo ============================================================
echo.
echo สคริปต์นี้จะ (ปิดหมด: Proton + Mullvad + WireGuard + Windscribe + WARP):
echo   1. configmain.json kill switch:
echo        no_proxy_mode=1 (บอตข้าม VPN code ทั้งหมด)
echo        + wg_enabled=0, use_host_vpn=0, wg_auto_gen=0
echo        + wg_fixnet1_switch=0, wg_hard_reset_on_start=0
echo        + windscribe_autostart=0, warp_autostart=0
echo   2. kill wireproxy.exe
echo   3. uninstall WireGuardTunnel services บน Windows (ขอ UAC)
echo   4. kill Python processes: host_wg_rotator / web_app / auto_create_guest
echo   5. ทุก emulator: force-stop WG/Proton/Mullvad apps + ลบ always-on VPN
echo        + flush iptables NAT/MANGLE + ลบ tun0 + ลบ adb reverse + ล้าง proxy
echo   6. flush DNS บน Windows
echo.
echo ============================================================
echo.

rem --- STEP 1: patch configmain.json (kill switch) ---
if not exist configmain.json (
    echo [!] ไม่พบ configmain.json - skip step 1
) else (
    echo [1/6] patch configmain.json (kill switch no_proxy_mode)...
    python -c "import json; p='configmain.json'; d=json.load(open(p,encoding='utf-8-sig')); d['no_proxy_mode']=1; d['wg_enabled']=0; d['use_host_vpn']=0; d['wg_auto_gen']=0; d['wg_regen_blocked']=0; d['wg_fixnet1_switch']=0; d['wg_hard_reset_on_start']=0; d['windscribe_autostart']=0; d['warp_autostart']=0; open(p,'w',encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=4)); print('    [OK] no_proxy_mode=1 (kill switch) + wg_enabled=0 + use_host_vpn=0 + autostart ปิดทุกตัว')"
    if errorlevel 1 (
        echo     [!] patch config ล้มเหลว
    )
)

echo.
echo [2/6] kill wireproxy.exe ที่ค้าง...
tasklist /FI "IMAGENAME eq wireproxy.exe" 2>nul | find /I "wireproxy.exe" >nul
if errorlevel 1 (
    echo     ไม่มี wireproxy.exe ค้าง - OK
) else (
    taskkill /F /IM wireproxy.exe 2>nul
    echo     [OK] killed
)

echo.
echo [3/6] uninstall WireGuardTunnel services...
net session >nul 2>&1
if errorlevel 1 (
    echo     [!] ต้อง Admin - กำลังขอ UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-Command','& { $svcs = Get-Service -Name ''WireGuardTunnel$*'' -ErrorAction SilentlyContinue; if (-not $svcs) { Write-Host ''    ไม่มี tunnel ค้าง - OK''; exit 0 }; $wg = ''C:\Program Files\WireGuard\wireguard.exe''; if (-not (Test-Path $wg)) { $wg = ''C:\Program Files (x86)\WireGuard\wireguard.exe'' }; if (-not (Test-Path $wg)) { Write-Host ''    WireGuard for Windows ไม่ได้ติดตั้ง - skip''; exit 0 }; foreach ($s in $svcs) { $name = $s.Name -replace ''^WireGuardTunnel\$'',''''; Write-Host ('''    uninstalling: '' + $name); & $wg /uninstalltunnelservice $name; Start-Sleep -Seconds 1 }; Start-Sleep -Seconds 2; Write-Host ''    [OK] uninstalled'' }'" >nul 2>&1
    rem รอ UAC window + command เสร็จ
    timeout /t 5 /nobreak >nul
    echo     [OK] UAC call sent
) else (
    powershell -NoProfile -Command "& { $svcs = Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue; if (-not $svcs) { Write-Host '    ไม่มี tunnel ค้าง - OK'; exit 0 }; $wg = 'C:\Program Files\WireGuard\wireguard.exe'; if (-not (Test-Path $wg)) { $wg = 'C:\Program Files (x86)\WireGuard\wireguard.exe' }; if (-not (Test-Path $wg)) { Write-Host '    WireGuard for Windows ไม่ได้ติดตั้ง - skip'; exit 0 }; foreach ($s in $svcs) { $name = $s.Name -replace '^WireGuardTunnel\$',''; Write-Host ('    uninstalling: ' + $name); & $wg /uninstalltunnelservice $name; Start-Sleep -Seconds 1 }; Start-Sleep -Seconds 2; Write-Host '    [OK] uninstalled' }"
)

echo.
echo [4/6] kill python processes ที่ใช้ WG (host_wg_rotator / web_app / auto_create_guest)...
for %%P in (host_wg_rotator.py web_app.py auto_create_guest.py) do (
    wmic process where "name='python.exe' and commandline like '%%%%%%P%%%%'" delete >nul 2>&1
    wmic process where "name='pythonw.exe' and commandline like '%%%%%%P%%%%'" delete >nul 2>&1
)
echo     [OK] ล้าง python processes ที่ค้าง (ถ้ามี)

echo.
echo [5/6] เคลียร์บนทุก emulator (WireGuard/Proton/Mullvad apps + iptables + always-on VPN)...

rem หา adb.exe
set "ADB=%~dp0adb\adb.exe"
if not exist "%ADB%" set "ADB=adb"

rem list devices แล้ว loop
set "DEV_FOUND=0"
for /f "skip=1 tokens=1" %%d in ('"%ADB%" devices 2^>nul') do (
    if not "%%d"=="" if not "%%d"=="List" (
        set /a DEV_FOUND+=1
        echo     [!DEV_FOUND!] %%d:
        rem force-stop VPN apps ทุกตัว (WireGuard / Proton / Mullvad / OpenVPN)
        for %%A in (com.wireguard.android ch.protonvpn.android net.mullvad.mullvadvpn net.openvpn.openvpn de.blinkt.openvpn) do (
            "%ADB%" -s %%d shell am force-stop %%A >nul 2>&1
        )
        rem ลบ always-on VPN setting (ไม่ให้ระบบ restart VPN เอง)
        "%ADB%" -s %%d shell settings delete global always_on_vpn_app >nul 2>&1
        "%ADB%" -s %%d shell settings delete global always_on_vpn_lockdown >nul 2>&1
        "%ADB%" -s %%d shell "su -c 'settings delete global always_on_vpn_app' 2>/dev/null" >nul 2>&1
        "%ADB%" -s %%d shell "su -c 'settings delete global always_on_vpn_lockdown' 2>/dev/null" >nul 2>&1
        rem ลบ tun0 interface (ถ้ามี)
        "%ADB%" -s %%d shell "su -c 'ip link set tun0 down 2>/dev/null; ip tuntap del tun0 mode tun 2>/dev/null' 2>/dev/null" >nul 2>&1
        rem ลบ iptables DNAT/REDIRECT rules ที่อาจค้าง
        "%ADB%" -s %%d shell "su -c 'iptables -t nat -D OUTPUT -p tcp ! -d 127.0.0.1 --dport 443 -j DNAT --to-destination 127.0.0.1:8443' 2>/dev/null" >nul 2>&1
        "%ADB%" -s %%d shell "su -c 'iptables -t nat -D OUTPUT -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8443' 2>/dev/null" >nul 2>&1
        rem flush mangle/nat tables (ลบ VPN routing rules ทั้งหมด - ต้อง root)
        "%ADB%" -s %%d shell "su -c 'iptables -t mangle -F; iptables -t nat -F OUTPUT' 2>/dev/null" >nul 2>&1
        rem ลบ adb reverse
        "%ADB%" -s %%d reverse --remove-all >nul 2>&1
        rem ล้าง http proxy
        "%ADB%" -s %%d shell settings put global http_proxy :0 >nul 2>&1
        echo         force-stopped VPN apps, lost always-on, flushed iptables/tun0/reverse/proxy
    )
)

if %DEV_FOUND% EQU 0 (
    echo     ไม่มี emulator ต่ออยู่ - skip
) else (
    echo     [OK] เคลียร์ %DEV_FOUND% เครื่อง
)

echo.
echo [6/6] reset ระบบ Windows network (flush DNS + release WG routes)...
ipconfig /flushdns >nul 2>&1
echo     [OK] DNS flushed

echo.
echo ============================================================
echo [DONE] ปิด VPN ทั้งหมดแล้ว
echo ============================================================
echo.
echo สถานะ:
echo   - บอตจะใช้ IP ตรงของเครื่อง/อีมู (ไม่ผ่าน WG)
echo   - config: wg_enabled=0, use_host_vpn=0
echo   - ไม่มี wireproxy.exe ค้าง, ไม่มี WG tunnel บน Windows
echo.
echo ตรวจว่าปิดสำเร็จ: ตอนรันบอตควรเห็นข้อความ:
echo   [NO-PROXY] no_proxy_mode=1 - ข้าม Windscribe/WG ทั้งหมด ใช้ IP เครื่องตรง ๆ
echo (แทนบรรทัด [CONFIG] FORCE Proton mode / [WG-INSTALL] / [WG] ต่อ VPN)
echo.
echo ถ้าต้องการเปิดกลับ:
echo   - edit configmain.json ตั้ง no_proxy_mode=0 + wg_enabled=1
echo   - หรือ enable-host-vpn.bat (เปิด host-mode)
echo.
pause
endlocal
exit /b 0
