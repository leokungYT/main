# EVPN-UI-AUTO.ps1 - click through ExpressVPN UI automatically
# Disables Lightway Turbo + enables Split Tunneling + Add IPs
# Uses Windows UI Automation API (System.Windows.Automation)
#
# Usage on remote PowerShell (as Administrator):
#   iwr https://raw.githubusercontent.com/leokungYT/main/main/EVPN-UI-AUTO.ps1 -UseB | iex

$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  EVPN-UI-AUTO: toggle ExpressVPN settings via UI clicks" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

function Start-EvpnUI {
    Stop-Process -Name "ExpressVPN" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    foreach ($p in @(
        "C:\Program Files (x86)\ExpressVPN\expressvpn-ui\ExpressVPN.exe",
        "C:\Program Files\ExpressVPN\expressvpn-ui\ExpressVPN.exe"
    )) {
        if (Test-Path $p) { Start-Process $p; break }
    }
    Start-Sleep -Seconds 8   # wait for UI to load
}

function Get-EvpnWindow {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $cond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, "ExpressVPN")
        $w = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
        if ($w) { return $w }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Find-ByName($parent, $name) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $name)
    return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Click-Element($el) {
    if (-not $el) { return $false }
    try {
        $pat = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        if ($pat) { $pat.Invoke(); return $true }
    } catch {}
    try {
        $tp = $el.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
        if ($tp) { $tp.Toggle(); return $true }
    } catch {}
    try {
        $sp = $el.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        if ($sp) { $sp.Select(); return $true }
    } catch {}
    return $false
}

Write-Host ""
Write-Host "[1/5] start ExpressVPN UI..." -ForegroundColor Yellow
Start-EvpnUI
$win = Get-EvpnWindow
if (-not $win) { Write-Host "[FAIL] cannot find ExpressVPN window" -ForegroundColor Red; exit 1 }
Write-Host "       UI ready" -ForegroundColor Green

Write-Host "[2/5] navigate Profile -> VPN Protocol..." -ForegroundColor Yellow
# click Profile tab
$profile = Find-ByName $win "Profile"
if ($profile) { Click-Element $profile | Out-Null; Start-Sleep -Seconds 2 }
# click VPN Protocol
$vpnProto = Find-ByName $win "VPN Protocol"
if ($vpnProto) { Click-Element $vpnProto | Out-Null; Start-Sleep -Seconds 2 }

Write-Host "[3/5] toggle Lightway Turbo OFF..." -ForegroundColor Yellow
$turbo = Find-ByName $win "Lightway Turbo"
if ($turbo) {
    try {
        $tp = $turbo.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
        if ($tp.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) {
            $tp.Toggle()
            Write-Host "       toggled OFF" -ForegroundColor Green
        } else {
            Write-Host "       already OFF" -ForegroundColor Green
        }
    } catch {
        # try finding nearby toggle
        Write-Host "       [WARN] toggle pattern not found - trying click" -ForegroundColor Yellow
        Click-Element $turbo | Out-Null
    }
    Start-Sleep -Seconds 1
} else {
    Write-Host "       [WARN] Lightway Turbo element not found" -ForegroundColor Yellow
}

Write-Host "[4/5] go back -> Split Tunneling -> toggle ON + Add IPs..." -ForegroundColor Yellow
# press back / navigate to Split Tunneling
$back = Find-ByName $win "Back"
if ($back) { Click-Element $back | Out-Null; Start-Sleep -Seconds 1 }
$split = Find-ByName $win "Split Tunneling"
if ($split) { Click-Element $split | Out-Null; Start-Sleep -Seconds 2 }

# toggle Split tunneling ON
$splitToggle = Find-ByName $win "Split tunneling"
if ($splitToggle) {
    try {
        $tp = $splitToggle.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
        if ($tp.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) {
            $tp.Toggle()
            Write-Host "       Split tunneling toggled ON" -ForegroundColor Green
        }
    } catch {}
    Start-Sleep -Seconds 1
}

# Click Add IP and type IPs
foreach ($ip in @("100.64.0.0/10","192.168.0.0/16")) {
    $addIp = Find-ByName $win "Add IP"
    if ($addIp) {
        Click-Element $addIp | Out-Null
        Start-Sleep -Milliseconds 800
        # type IP via SendKeys (dialog expects IP input field)
        [System.Windows.Forms.SendKeys]::SendWait($ip)
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 1
        Write-Host "       added IP: $ip" -ForegroundColor Green
    } else {
        Write-Host "       [WARN] Add IP button not found for $ip" -ForegroundColor Yellow
    }
}

Write-Host "[5/5] save + close settings..." -ForegroundColor Yellow
$done = Find-ByName $win "Done"
if (-not $done) { $done = Find-ByName $win "Save" }
if (-not $done) { $done = Find-ByName $win "OK" }
if ($done) { Click-Element $done | Out-Null; Start-Sleep -Seconds 1 }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DONE - verify in ExpressVPN UI manually" -ForegroundColor Green
Write-Host "  If anything missed: redo it by hand this one time" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green
