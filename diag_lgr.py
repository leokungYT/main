"""ตรวจเครื่องบอท LGR - หาว่าทำไม adb timeout / offline / fixid
รัน: python diag_lgr.py  (หรือดับเบิลคลิก diag-lgr.bat) แล้วส่งไฟล์ diag-report.txt มาให้ดู
อ่านอย่างเดียว ไม่แก้อะไรในเครื่อง
"""
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(HERE, "adb", "adb.exe")
if not os.path.exists(ADB):
    ADB = "adb"
NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def run(cmd, timeout=20, shell=False):
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, shell=shell, **NOWIN)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace"), time.time() - t
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT", time.time() - t
    except Exception as e:
        return -2, str(e), time.time() - t


def ps(script, timeout=30):
    return run(["powershell", "-NoProfile", "-Command", script], timeout)[1].strip()


say("=" * 60)
say(" LGR diag  " + time.strftime("%Y-%m-%d %H:%M:%S"))
say("=" * 60)

# 1) เครื่องหนักไหม
say("\n[1] CPU / RAM")
say(ps("$c=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
       "$o=Get-CimInstance Win32_OperatingSystem;"
       "'CPU load: ' + $c + '%  | cores: ' + (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum;"
       "'RAM: used ' + [math]::Round(($o.TotalVisibleMemorySize-$o.FreePhysicalMemory)/1MB,1) + ' / ' + [math]::Round($o.TotalVisibleMemorySize/1MB,1) + ' GB'"))

# 2) VPN บนเครื่องหลัก (ตัวต้องสงสัยอันดับ 1)
say("\n[2] VPN / network adapters ที่เปิดอยู่บนเครื่องหลัก")
say(ps("Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { $_.Name + '  |  ' + $_.InterfaceDescription }"))
vpn_procs = ["Surfshark", "tailscale", "Cloudflare", "warp-svc", "RvRvpnGui", "RadminVPN", "wireguard", "openvpn", "nordvpn", "expressvpn", "ProtonVPN", "Windscribe"]
_, tl, _ = run(["tasklist"])
found = sorted({p for p in vpn_procs for line in tl.splitlines() if line.lower().startswith(p.lower())})
say("โปรแกรม VPN ที่รันอยู่: " + (", ".join(found) if found else "ไม่พบ"))

# 3) adb หลายตัวแย่งกัน
say("\n[3] adb ที่รันอยู่ (ควรมีตัวเดียว)")
say(ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'adb' } | ForEach-Object { $_.Name + '  ' + $_.ExecutablePath }") or "ไม่มี")
say(ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' } | Measure-Object | ForEach-Object { 'python processes: ' + $_.Count }"))

# 4) ทีละจอ
say("\n[4] ทีละจอ (state / เวลา screencap / tunnel VPN / ออกเน็ต)")
_, out, _ = run([ADB, "devices"], 15)
devs = []
for line in out.splitlines()[1:]:
    p = line.split()
    if len(p) >= 2:
        devs.append((p[0], p[1]))
say(f"adb devices: {len(devs)} รายการ")
for d, st in devs:
    if st != "device":
        say(f"  {d:22s} state={st}  <-- ใช้ไม่ได้")
        continue
    times = []
    for _ in range(3):
        rc, _o, dt = run([ADB, "-s", d, "exec-out", "screencap", "-p"], 15)
        times.append("TIMEOUT" if rc == -1 else f"{dt:.1f}s")
    _, tun, _ = run([ADB, "-s", d, "shell", "ip -o link show | grep -c tun"], 10)
    _, png, _ = run([ADB, "-s", d, "shell", "ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1 && echo OK || echo FAIL"], 12)
    _, game, _ = run([ADB, "-s", d, "shell", "ping -c 1 -W 3 rangers-api.line-apps.com >/dev/null 2>&1 && echo OK || echo FAIL"], 12)
    say(f"  {d:22s} screencap {', '.join(times):24s} vpn_tun={tun.strip() or '?'}  net={png.strip()}  line-api={game.strip()}")

say("\n[อ่านผล]")
say("- [2] มี Surfshark/Tailscale/WARP/Radmin เปิดอยู่  -> ลองปิดแล้วรันบอทใหม่ (ตัวต้องสงสัยอันดับ 1)")
say("- [3] adb มากกว่า 1 ตัว / คนละ path              -> มีโปรแกรมอื่นแย่ง adb (PES, ตัวจัดการ MuMu ฯลฯ)")
say("- [1] CPU > 90% หรือ RAM ใกล้เต็ม                -> เครื่องรับจอไม่ไหว ลดจำนวนจอ")
say("- [4] screencap เกิน 3s / TIMEOUT เฉพาะบางจอ      -> จอนั้นมีปัญหา ปิด-เปิดจอนั้นใน MuMu")
say("- [4] net=FAIL หรือ line-api=FAIL                -> เน็ต/VPN ในจอนั้นออกไม่ได้")

with open(os.path.join(HERE, "diag-report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(OUT) + "\n")
say(f"\nบันทึกไว้ที่ {os.path.join(HERE, 'diag-report.txt')} - ส่งไฟล์นี้มาให้ดู")
