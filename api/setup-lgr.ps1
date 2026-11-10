# api/setup-lgr.ps1
# one-shot: adb connect + push cert + install to /system + reboot + set proxy + launch mitmweb
# usage:
#   cd C:\Users\Administrator\Downloads\LGR
#   powershell -ExecutionPolicy Bypass -File api\setup-lgr.ps1

$ErrorActionPreference = "Stop"

$SER   = "127.0.0.1:7555"
$PORT  = 8888
$REPO  = "C:\Users\Administrator\Downloads\LGR"
$CERT  = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.pem"

Write-Host "[1/7] starting mitmweb to generate CA (5s)..."
if (-not (Test-Path $CERT)) {
    $job = Start-Process -FilePath "mitmweb" -PassThru -WindowStyle Hidden `
           -ArgumentList "--listen-port",$PORT,"--web-port","8081"
    Start-Sleep -Seconds 5
    Stop-Process -Id $job.Id -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path $CERT)) { throw "cert not found at $CERT" }
Write-Host "    cert ok: $CERT"

Write-Host "[2/7] adb connect $SER ..."
adb kill-server | Out-Null
adb start-server | Out-Null
adb connect $SER | Out-Null
$dev = adb devices | Select-String $SER
if (-not $dev) { throw "adb cannot see $SER - open MuMu first" }

Write-Host "[3/7] push cert to emu ..."
adb -s $SER push $CERT /sdcard/mitm.pem | Out-Null

Write-Host "[4/7] install cert to /system (root required) ..."
$script = @'
HASH=$(openssl x509 -subject_hash_old -in /sdcard/mitm.pem -noout)
echo HASH=$HASH
mount -o rw,remount /system
cp /sdcard/mitm.pem /system/etc/security/cacerts/${HASH}.0
chmod 644 /system/etc/security/cacerts/${HASH}.0
mount -o ro,remount /system
ls -la /system/etc/security/cacerts/${HASH}.0
'@
adb -s $SER shell "su -c '$script'"

Write-Host "[5/7] reboot MuMu (wait 35s) ..."
adb -s $SER reboot | Out-Null
Start-Sleep -Seconds 35
adb connect $SER | Out-Null

Write-Host "[6/7] set proxy on emu ..."
$PC = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "169.*" -and $_.IPAddress -ne "127.0.0.1" -and $_.InterfaceAlias -notmatch "Loopback|vEthernet" } |
       Select-Object -First 1).IPAddress
if (-not $PC) { throw "cannot find PC IP" }
Write-Host "    PC IP = $PC"
adb -s $SER shell settings put global http_proxy  "${PC}:${PORT}"
adb -s $SER shell settings put global https_proxy "${PC}:${PORT}"
$cur = adb -s $SER shell settings get global http_proxy
Write-Host "    proxy set: $cur"

Write-Host "[7/7] launching mitmweb (foreground) ..."
Write-Host "    UI at http://127.0.0.1:8081"
Write-Host "    open LGR in MuMu - traffic will appear"
Write-Host ""
Set-Location $REPO
mitmweb --listen-port $PORT --web-port 8081 -s "$REPO\api\lgr_sniff.py"
