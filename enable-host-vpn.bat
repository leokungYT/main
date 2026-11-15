@echo off
REM enable-host-vpn.bat - set use_host_vpn=1 in configmain.json
REM After: stop bot, run this, start bot. All per-emu WG goes OFF, host rotator takes over.

cd /d "%~dp0"

if not exist configmain.json (
    echo [ERR] configmain.json not found in %cd%
    pause
    exit /b 1
)

python -c "import json; p='configmain.json'; d=json.load(open(p,encoding='utf-8')); d['use_host_vpn']=1; d['host_vpn_rotate_min']=d.get('host_vpn_rotate_min',7); d['host_vpn_split_domains']=['rangers-api.line-apps.com','game-api.line.me','obs.line-apps.com','obs.line-scdn.net','access.line.me','api.line.me']; open(p,'w',encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=4)); print('[OK] use_host_vpn =', d['use_host_vpn']); print('[OK] host_vpn_rotate_min =', d['host_vpn_rotate_min']); print('[OK] host_vpn_split_domains =', d['host_vpn_split_domains'])"

if %errorlevel% neq 0 (
    echo [ERR] Failed to patch configmain.json
    pause
    exit /b 1
)

echo.
echo [OK] configmain.json patched - use_host_vpn is now ON
echo.
echo Next:
echo   1. host-wg-rotate.bat     (keep window open - handles the VPN on Windows)
echo   2. Start the bot as usual (per-emu WG will be skipped automatically)
echo.
echo To disable: run disable-host-vpn.bat
pause
