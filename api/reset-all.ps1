# reset-all.ps1 - kill WG + mitm + strip emu iptables/hosts; leaves emu ready for a fresh run

param(
    [string] $Serial = "127.0.0.1:7555"
)

$ErrorActionPreference = "Continue"

Write-Host "[*] killing wireproxy / mitmdump on PC"
Get-Process wireproxy -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process mitmdump  -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python    -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -match "mitm"
} | Stop-Process -Force

Write-Host "[*] stripping emu iptables + hosts bind + adb reverse"
& adb -s $Serial reverse --remove-all 2>$null
& adb -s $Serial shell "su -c 'iptables -t nat -F OUTPUT; umount /system/etc/hosts 2>/dev/null; echo ok'" 2>&1

Write-Host "[*] force-stop LGR"
& adb -s $Serial shell "am force-stop com.linecorp.LGRGS"

Write-Host "[+] reset done - now re-run run-replay-all.ps1 without -Skip"
