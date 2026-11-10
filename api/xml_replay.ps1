# xml_replay.ps1 - push xml -> emu -> wait for mitm to capture -> api check
# Precondition: mitmdump + wg-proxy + emu routing already up (run-replay-all.ps1 does all)
#
# Usage:
#   .\xml_replay.ps1 -XmlDir "C:\...\login-success" -Serial 127.0.0.1:7555
#   .\xml_replay.ps1 -XmlFile ".\one.xml" -Serial 127.0.0.1:7555
#   .\xml_replay.ps1 -XmlDir "..." -WaitSec 25 -Limit 5

param(
    [string] $XmlDir,
    [string] $XmlFile,
    [string] $Serial = "127.0.0.1:7555",
    [int]    $WaitSec = 20,
    [int]    $Limit = 0
)

$ErrorActionPreference = "Stop"
$pkg      = "com.linecorp.LGRGS"
$actv     = "com.linecorp.LGRGS/com.linecorp.LGRGS.LineRangersAdr"
$prefPath = "/data/data/$pkg/shared_prefs/_LINE_COCOS_PREF_KEY.xml"

function Invoke-Adb {
    param([string[]] $AdbArgs)
    & adb -s $Serial @AdbArgs
}

function Push-OneXml {
    param([string] $local)
    Write-Host "[*] push $(Split-Path $local -Leaf)"
    Invoke-Adb @("push", $local, "/sdcard/_lgr_prefs.xml") | Out-Null
    $uid = (Invoke-Adb @("shell", "su -c 'stat -c %u /data/data/$pkg'")).Trim()
    $cmd = "cp /sdcard/_lgr_prefs.xml $prefPath && chown ${uid}:${uid} $prefPath && chmod 660 $prefPath"
    Invoke-Adb @("shell", "su -c '$cmd'") | Out-Null
}

function Restart-LGR {
    Invoke-Adb @("shell", "am force-stop $pkg") | Out-Null
    Start-Sleep -Milliseconds 400
    Invoke-Adb @("shell", "am start -n $actv") | Out-Null
}

function Get-RsnFromName {
    param([string] $name)
    if ($name -match '([0-9a-f]{8})_LINE_COCOS') { return $Matches[1] }
    return $null
}

function Check-OneAccount {
    param([string] $rsn)
    if (-not $rsn) { return $null }
    return (& python "$PSScriptRoot\_check_rsn.py" $rsn) -join "`n"
}

# ===== main =====
if ($XmlFile) {
    $xmls = @(Get-Item $XmlFile)
} elseif ($XmlDir) {
    $xmls = Get-ChildItem -Path $XmlDir -Filter "*.xml"
    if ($Limit -gt 0) { $xmls = $xmls | Select-Object -First $Limit }
} else {
    throw "need -XmlDir or -XmlFile"
}

Write-Host "[CFG] serial=$Serial  wait=${WaitSec}s  count=$($xmls.Count)"

$ok = 0; $dead = 0; $miss = 0
foreach ($x in $xmls) {
    $rsn = Get-RsnFromName $x.Name
    Write-Host "--- $($x.Name) (rsn=$rsn) ---"

    Push-OneXml -local $x.FullName
    Restart-LGR
    Start-Sleep -Seconds $WaitSec

    # kill game BEFORE checking - stops it from retrying /login and rotating
    # the just-captured guestCookie out from under us
    Invoke-Adb @("shell", "am force-stop $pkg") | Out-Null
    Start-Sleep -Seconds 2

    $r = Check-OneAccount -rsn $rsn
    Write-Host $r
    if     ($r -match '^OK')   { $ok++ }
    elseif ($r -match '^DEAD') { $dead++ }
    else                       { $miss++ }
}

Write-Host ""
Write-Host "=== ok=$ok dead=$dead miss=$miss total=$($xmls.Count) ==="
