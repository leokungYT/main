# -*- coding: utf-8 -*-
"""proxy_switcher.py - ตั้ง Android http_proxy ของแต่ละจอให้ใช้ free proxy

หลักการ: Android มี setting 'global http_proxy' - ตั้งแล้ว ทุก app รวมเกม
  จะวิ่งผ่าน proxy นั้นอัตโนมัติ (รวม LGR API, LineGame.co.jp)
  = ไม่ต้องใช้ WG, ไม่ต้องติดตั้ง app, แค่สั่ง adb shell

ใช้:
  python proxy_switcher.py                   # แจก proxy จาก free_proxies_residential.txt ทุกจอ
  python proxy_switcher.py --country TH      # เฉพาะ proxy ไทย
  python proxy_switcher.py --clear           # ล้าง proxy ออกทุกจอ
  python proxy_switcher.py --test <ip:port>  # test proxy ตัวเดียว LGR ตอบไหม

ขั้นตอน:
  1) อ่าน free_proxies_residential.txt / free_proxies_working.txt
  2) filter ตาม --country (ถ้าระบุ)
  3) adb devices -> list emulator
  4) แจก proxy ให้แต่ละจอ (round-robin): adb shell settings put global http_proxy ip:port
  5) print mapping device -> proxy

หลังรันแล้ว: ปิด wg_enabled=0 ใน configmain.json แล้วรัน bot ตามปกติ
  bot จะใช้ Android http_proxy ที่ตั้งไว้ -> traffic วิ่งผ่าน TOT/VNPT/etc.
  -> LGR เห็น IP residential -> 401 ผ่าน
"""
import os
import random
import re
import subprocess
import sys


ADB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adb", "adb.exe")
RES_FILE = "free_proxies_residential.txt"
WORK_FILE = "free_proxies_working.txt"


def sh(args, timeout=15):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=0x08000000 if os.name == "nt" else 0).stdout
    except Exception as e:
        return ""


def load_proxies(country=None, residential_only=False):
    """อ่าน proxy จากไฟล์ที่ scraper สร้าง - filter ตาม country ถ้าระบุ"""
    fname = RES_FILE if residential_only else WORK_FILE
    if not os.path.exists(fname):
        print(f"[!] ไม่พบไฟล์ {fname} - รัน 'python free_proxy_scraper.py' ก่อน")
        return []
    out = []
    with open(fname, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # format: http://ip:port  # isp=X country=Y kind=Z
            m = re.match(r"(https?|socks5)://([^:]+):(\d+)\s*(?:#(.*))?", line)
            if not m:
                continue
            proto, ip, port, meta = m.group(1), m.group(2), int(m.group(3)), m.group(4) or ""
            country_in = ""
            if "country=" in meta:
                country_in = meta.split("country=")[1].split()[0]
            kind = ""
            if "kind=" in meta:
                kind = meta.split("kind=")[1].split()[0]
            # ข้าม socks5 (Android global http_proxy ไม่รองรับ socks5)
            if proto != "http":
                continue
            # filter country
            if country and country.upper() not in country_in.upper():
                continue
            out.append({"proto": proto, "ip": ip, "port": port,
                        "country": country_in, "kind": kind})
    return out


def list_devices():
    out = sh([ADB, "devices"])
    devs = []
    for line in out.splitlines()[1:]:
        if line.strip().endswith("device"):
            devs.append(line.split()[0])
    return devs


def set_proxy(dev, ip, port):
    """ตั้ง Android global http_proxy = ip:port สำหรับ app ทุกตัวในจอนี้"""
    sh([ADB, "-s", dev, "shell", f"settings put global http_proxy {ip}:{port}"])
    # เช็ค
    r = sh([ADB, "-s", dev, "shell", "settings get global http_proxy"]).strip()
    return r


def clear_proxy(dev):
    """ล้าง Android http_proxy"""
    sh([ADB, "-s", dev, "shell", "settings delete global http_proxy"])
    sh([ADB, "-s", dev, "shell", "settings put global http_proxy :0"])
    sh([ADB, "-s", dev, "shell", "settings delete global http_proxy"])
    r = sh([ADB, "-s", dev, "shell", "settings get global http_proxy"]).strip()
    return r


def test_proxy(ip, port):
    """ยิง LGR API ผ่าน proxy ดู code - 401 = ใช้ได้"""
    import urllib.request
    proxy_url = f"http://{ip}:{port}"
    handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    opener = urllib.request.build_opener(handler)
    try:
        r = opener.open("https://rangers-api.line-apps.com/v12.3/home", timeout=10)
        return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"error: {e}"


def main():
    args = sys.argv[1:]

    # test proxy ตัวเดียว
    if "--test" in args:
        p = args[args.index("--test") + 1]
        ip, port = p.split(":", 1) if ":" in p else (p, "80")
        print(f"[test] ยิง LGR API ผ่าน {ip}:{port}...")
        code = test_proxy(ip, int(port))
        if code in (401, 200):
            print(f"[OK] code {code} - proxy ใช้ได้กับ LGR")
        else:
            print(f"[X] code {code} - proxy ไม่ผ่าน LGR")
        return

    # clear mode
    if "--clear" in args:
        devs = list_devices()
        print(f"[clear] ล้าง http_proxy ทุกจอ ({len(devs)} จอ)...")
        for d in devs:
            r = clear_proxy(d)
            print(f"  {d}: {r or '(ว่าง)'}")
        print("[OK] ล้างเสร็จ")
        return

    # assign mode
    country = None
    if "--country" in args:
        country = args[args.index("--country") + 1]

    # ลอง residential ก่อน ถ้าว่างใช้ working ทั้งหมด
    proxies = load_proxies(country=country, residential_only=True)
    if not proxies:
        print(f"[!] ไม่มี residential proxy - fallback ใช้ working ทั้งหมด")
        proxies = load_proxies(country=country, residential_only=False)
    if not proxies:
        print(f"[X] ไม่มี proxy เลย - รัน free_proxy_scraper.py ก่อน")
        return

    print(f"[proxies] โหลด {len(proxies)} proxies" + (f" (country={country})" if country else ""))
    for i, p in enumerate(proxies[:10], 1):
        print(f"  [{i}] http://{p['ip']}:{p['port']} ({p['country']}, {p['kind']})")
    if len(proxies) > 10:
        print(f"  ... อีก {len(proxies) - 10} ตัว")

    devs = list_devices()
    if not devs:
        print("[X] ไม่พบจอ emulator - เปิด MuMu ก่อน")
        return

    print(f"\n[devices] {len(devs)} จอ - แจก proxy แบบ round-robin...")

    # ทดสอบ proxy ก่อนแจก - เอาเฉพาะที่ยัง live
    print(f"[verify] ทดสอบ proxy แต่ละตัว (10s/ตัว)...")
    alive = []
    for p in proxies[:len(devs) * 2]:  # ทดสอบแค่ 2x จำนวนจอ
        code = test_proxy(p["ip"], p["port"])
        if code in (401, 200):
            print(f"  ✓ {p['ip']}:{p['port']} ({p['country']}) - code {code}")
            alive.append(p)
            if len(alive) >= len(devs):
                break
        else:
            print(f"  ✗ {p['ip']}:{p['port']} ({p['country']}) - code {code}")

    if not alive:
        print("[X] ไม่มี proxy ที่ยังใช้ได้ - รัน scraper ใหม่")
        return

    print(f"\n[assign] proxy ที่ใช้ได้ {len(alive)} ตัว - แจก {len(devs)} จอ:")
    for i, d in enumerate(devs):
        p = alive[i % len(alive)]
        r = set_proxy(d, p["ip"], p["port"])
        print(f"  {d} -> http://{p['ip']}:{p['port']} ({p['country']}) | setting={r}")

    print(f"\n[OK] แจก proxy เสร็จ {len(devs)} จอ")
    print(f"     ขั้นถัดไป: ปิด wg_enabled=0 ใน configmain.json แล้ว python login.py")


if __name__ == "__main__":
    main()
