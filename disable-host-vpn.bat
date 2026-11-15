@echo off
REM disable-host-vpn.bat - set use_host_vpn=0 in configmain.json (revert to per-emu WG)

cd /d "%~dp0"

if not exist configmain.json (
    echo [ERR] configmain.json not found
    pause
    exit /b 1
)

python -c "import json; p='configmain.json'; d=json.load(open(p,encoding='utf-8')); d['use_host_vpn']=0; open(p,'w',encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=4)); print('[OK] use_host_vpn =', d['use_host_vpn'])"

echo.
echo [OK] configmain.json patched - use_host_vpn is now OFF (per-emu WG mode)
echo.
echo Also stop the host rotator if running: host-wg-rotate.bat --stop
echo (or host-wg-kill.bat to force-remove any stuck tunnel)
pause
