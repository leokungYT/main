# ================================================================
# MITM-GO.ps1 — one-click launcher
# double-click to run (or: powershell -ExecutionPolicy Bypass -File .\MITM-GO.ps1)
# ================================================================

$ErrorActionPreference = 'Continue'
trap { Write-Host "`n[FATAL] $_" -ForegroundColor Red; Write-Host $_.ScriptStackTrace -ForegroundColor DarkYellow; Read-Host "`nEnter to close"; exit 1 }
Start-Transcript -Path "$PSScriptRoot\MITM-GO.log" -Force | Out-Null

$repo    = 'c:\Users\leoku\Downloads\LGR\main'
$adb     = Join-Path $repo 'adb\adb.exe'
$addon   = Join-Path $repo 'api\mitm_lgr.py'
$mitmweb = "$env:APPDATA\Python\Python311\Scripts\mitmweb.exe"
$port    = 8080
$webPort = 8081
$hostIP  = '192.168.56.1'

Set-Location $repo
Write-Host "`n=== MITM-GO ===" -ForegroundColor Cyan

# --- 1. launch mitmweb bind 0.0.0.0 ใน window ใหม่ ---
if (-not (Get-Process mitmweb -ErrorAction SilentlyContinue)) {
    Write-Host "[1] launching mitmweb..." -ForegroundColor Yellow
    Start-Process -FilePath $mitmweb -ArgumentList `
        "-s",$addon,"--listen-host","0.0.0.0","--listen-port",$port,"--web-port",$webPort `
        -WindowStyle Normal
    Start-Sleep 4
} else {
    Write-Host "[1] mitmweb already running" -ForegroundColor Green
}

# --- 2. เช็ค cert เกิดแล้วยัง (mitm gen ตอน start ครั้งแรก) ---
$cert = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
if (-not (Test-Path $cert)) {
    Write-Host "[!] cert ยังไม่เกิด รอ 3 วิ..." -ForegroundColor Yellow
    Start-Sleep 3
}

# --- 3. ADB: kill-server, start, TCP scan, connect ---
Write-Host "[2] starting adb..." -ForegroundColor Yellow
Get-Process adb,adb_server,nox_adb -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
& $adb start-server | Out-Null

function Test-PortOpen($p) {
    $t = New-Object System.Net.Sockets.TcpClient
    $iar = $t.BeginConnect('127.0.0.1',$p,$null,$null)
    $ok = $iar.AsyncWaitHandle.WaitOne(80,$false)
    $r = ($ok -and $t.Connected); $t.Close(); return $r
}

Write-Host "[3] scanning emulator ports..." -ForegroundColor Yellow
$open = 5555..5755 | Where-Object { $_ % 2 -eq 1 } | Where-Object { Test-PortOpen $_ }
foreach ($p in $open) { & $adb connect "127.0.0.1:$p" | Out-Null }

$dev = (& $adb devices) | Where-Object { $_ -match '\tdevice$' } | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1
if (-not $dev) {
    Write-Host "[!] ไม่พบ emulator online — เปิด emulator แล้วรันใหม่" -ForegroundColor Red
    Read-Host "`nEnter เพื่อปิด"
    exit 1
}
Write-Host "[+] device: $dev" -ForegroundColor Green

# --- 4. set proxy + push cert + kill LGR ---
Write-Host "[4] setting proxy + pushing cert..." -ForegroundColor Yellow
& $adb -s $dev shell settings put global http_proxy "${hostIP}:${port}" | Out-Null
$cur = (& $adb -s $dev shell settings get global http_proxy).Trim()
Write-Host "    proxy = $cur"

if (Test-Path $cert) {
    & $adb -s $dev push $cert /sdcard/mitmproxy-ca-cert.cer | Out-Null
    Write-Host "    cert pushed → /sdcard/"
}
& $adb -s $dev shell am force-stop com.linecorp.LGRGS 2>$null | Out-Null

# --- 5. หา launcher activity + เปิด LGR auto ---
$resolve = & $adb -s $dev shell "cmd package resolve-activity --brief com.linecorp.LGRGS" 2>&1
$launcher = ($resolve | Select-String '/' | Select-Object -Last 1).ToString().Trim()
if ($launcher -and $launcher -like 'com.linecorp.LGRGS/*') {
    Write-Host "[5] launching LGR: $launcher" -ForegroundColor Yellow
    & $adb -s $dev shell am start -n $launcher | Out-Null
} else {
    & $adb -s $dev shell monkey -p com.linecorp.LGRGS -c android.intent.category.LAUNCHER 1 | Out-Null
    Write-Host "[5] launched LGR via monkey" -ForegroundColor Yellow
}

# --- 6. เปิด mitmweb UI ---
Start-Process "http://127.0.0.1:$webPort"

Write-Host "`n=== READY ===" -ForegroundColor Green
Write-Host "  mitmweb UI : http://127.0.0.1:$webPort"
Write-Host "  proxy      : ${hostIP}:$port"
Write-Host "  device     : $dev"
Write-Host "  log        : $repo\api\mitm_lgr.log"
Write-Host "`nถ้า LGR pin cert ไม่เห็น flow:"
Write-Host "  .\MITM-GO.ps1 -Frida" -ForegroundColor Cyan

# --- optional: -Frida flag ยิง SSL unpin ---
if ($args -contains '-Frida') {
    Write-Host "`n[6] launching Frida SSL unpin..." -ForegroundColor Yellow
    # push + start frida-server
    $fridaLocal = Join-Path $repo 'frida-server'
    if (Test-Path $fridaLocal) {
        & $adb -s $dev root | Out-Null
        Start-Sleep 1
        & $adb -s $dev push $fridaLocal /data/local/tmp/frida-server | Out-Null
        & $adb -s $dev shell "chmod 755 /data/local/tmp/frida-server" | Out-Null
        Start-Process -NoNewWindow $adb -ArgumentList "-s",$dev,"shell","/data/local/tmp/frida-server"
        Start-Sleep 2
    }
    frida -U -f com.linecorp.LGRGS -l (Join-Path $repo 'api\LGR-frida-ssl-capture.js')
}

Read-Host "`nEnter เพื่อปิด"
