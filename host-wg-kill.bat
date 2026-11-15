@echo off
REM host-wg-kill.bat - force-remove ALL WireGuard tunnels on this PC
REM Use when cmd rotator was closed but tunnels still running as Windows services
REM (wireguard.exe /installtunnelservice creates persistent services that survive cmd close)

REM --- auto elevate to Admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [KILL] Need Administrator rights - requesting UAC...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath 'cmd.exe' -ArgumentList '/k','""%~f0""'"
    exit /b
)

set "WG_EXE=C:\Program Files\WireGuard\wireguard.exe"
if not exist "%WG_EXE%" set "WG_EXE=C:\Program Files (x86)\WireGuard\wireguard.exe"

if not exist "%WG_EXE%" (
    echo [KILL] WireGuard for Windows not found - nothing to kill
    pause
    exit /b 0
)

echo [KILL] Looking for WireGuardTunnel services...
echo.

REM List all WireGuardTunnel$ services and uninstall each
powershell -NoProfile -Command ^
  "$svcs = Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue;" ^
  "if (-not $svcs) { Write-Host '[KILL] No active WireGuard tunnels'; exit 0 };" ^
  "foreach ($s in $svcs) {" ^
  "  $name = $s.Name -replace '^WireGuardTunnel\$','';" ^
  "  Write-Host ('[KILL] uninstalling tunnel: ' + $name);" ^
  "  & '%WG_EXE%' /uninstalltunnelservice $name;" ^
  "  Start-Sleep -Seconds 1;" ^
  "};" ^
  "Start-Sleep -Seconds 2;" ^
  "$left = Get-Service -Name 'WireGuardTunnel$*' -ErrorAction SilentlyContinue;" ^
  "if ($left) { Write-Host '[KILL] WARNING: some services remain:'; $left | Format-Table Name,Status } else { Write-Host '[KILL] all tunnels removed OK' }"

echo.
echo [KILL] Done. AnyDesk / Chrome Remote Desktop should be reachable again.
echo [KILL] (If they still can't reach you, give it 5-10 sec for routes to clear)
pause
