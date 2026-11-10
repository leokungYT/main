# run-replay-all.ps1 - one-shot: WG + mitm + routing + replay
# Usage:
#   .\run-replay-all.ps1                            # all xmls in default folder
#   .\run-replay-all.ps1 -Limit 5                   # first 5 only
#   .\run-replay-all.ps1 -XmlFile ".\one.xml"       # single file
#   .\run-replay-all.ps1 -Serial 127.0.0.1:16384    # other emu
#   .\run-replay-all.ps1 -Skip "wg,mitm"            # skip if already up

param(
    [string] $XmlDir  = "C:\Users\Administrator\Downloads\LGR\login-success",
    [string] $XmlFile = "",
    [string] $Serial  = "127.0.0.1:7555",
    [int]    $WaitSec = 25,
    [int]    $Limit   = 0,
    [string] $Skip    = "",
    [string] $WgConf  = "ip-mullvad-1\Mullvad-key1-jp-tyo-wg-001.conf"
)

$ErrorActionPreference = "Stop"
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$skips = ($Skip -split ",") | ForEach-Object { $_.Trim().ToLower() }

function Test-Listen($port) {
    $hit = netstat -ano | Select-String ":$port\s+.*LISTENING"
    return ($hit -ne $null)
}

# ===== 1) WG proxy (socks5 1080 + tcp tunnel 9443) =====
if (($skips -contains "wg") -or (Test-Listen 1080)) {
    Write-Host "[=] WG already listening on 1080 - skip"
} else {
    $confFull = Join-Path (Split-Path $here -Parent) "wg\$WgConf"
    if (-not (Test-Path $confFull)) { throw "WG conf not found: $confFull" }
    Write-Host "[*] WG: launching wg-proxy.bat with $WgConf"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k","wg-proxy.bat `"$WgConf`"" -WorkingDirectory $here
    for ($i = 0; $i -lt 20; $i++) { if (Test-Listen 1080) { break }; Start-Sleep 1 }
    if (-not (Test-Listen 1080)) { throw "WG tunnel failed to open 1080 (check the cmd window for the real error)" }
    Write-Host "[+] WG ready - socks5://127.0.0.1:1080"
}

try {
    $ip = (& curl.exe -s --socks5 127.0.0.1:1080 --max-time 6 https://ifconfig.me).Trim()
    Write-Host "[+] WG exit IP = $ip"
} catch {
    Write-Host "[!] skip ip check"
}

# ===== 2) mitmdump reverse-proxy =====
if (($skips -contains "mitm") -or (Test-Listen 8443)) {
    Write-Host "[=] mitm already listening on 8443 - skip"
} else {
    Write-Host "[*] mitm: launching mitmdump in new window"
    $mitmCmd = 'mitmdump --mode reverse:https://127.0.0.1:9443 --listen-port 8443 --set upstream_cert=false --set connection_strategy=lazy --set keep_host_header=true -s capture_credential.py -q'
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k",$mitmCmd -WorkingDirectory $here
    for ($i = 0; $i -lt 15; $i++) { if (Test-Listen 8443) { break }; Start-Sleep 1 }
    if (-not (Test-Listen 8443)) { throw "mitmdump failed to open 8443" }
    Write-Host "[+] mitm ready - :8443 -> 127.0.0.1:9443 (via WG)"
}

# ===== 3) emu routing (push setup-routing.sh then exec as root) =====
Write-Host "[*] emu routing: push setup-routing.sh then run via su"
& adb -s $Serial reverse tcp:8443 tcp:8443 | Out-Null

$setupLocal  = Join-Path $here "setup-routing.sh"
$setupRemote = "/data/local/tmp/setup-routing.sh"
if (-not (Test-Path $setupLocal)) { throw "missing $setupLocal" }

& adb -s $Serial push $setupLocal $setupRemote | Out-Null
& adb -s $Serial shell "chmod 755 $setupRemote" | Out-Null
$routingLog = & adb -s $Serial shell "su -c 'sh $setupRemote'" 2>&1
$routingLog | ForEach-Object { Write-Host "    [emu] $_" }
if ($routingLog -match "Permission denied|operation not permitted") {
    Write-Host "[!] iptables denied - emu su may not be in nat table context"
    Write-Host "    hosts bind may still carry traffic via adb reverse; continuing"
}
Write-Host "[+] routing applied"

# ===== 4) replay =====
$replayScript = Join-Path $here "xml_replay.ps1"
if (-not (Test-Path $replayScript)) { throw "missing $replayScript" }

if ($XmlFile) {
    & $replayScript -XmlFile $XmlFile -Serial $Serial -WaitSec $WaitSec
} elseif ($Limit -gt 0) {
    & $replayScript -XmlDir $XmlDir -Serial $Serial -WaitSec $WaitSec -Limit $Limit
} else {
    & $replayScript -XmlDir $XmlDir -Serial $Serial -WaitSec $WaitSec
}
