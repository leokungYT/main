#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ip_check.py - เช็คว่า IP ตอนนี้ยิง rangers-api ได้ไหม (ไม่ต้อง creds.json)

หลักการ:
  - ยิง GET /v12.3/home โดย"ไม่ใส่ cookie"
  - server ตอบ 401/409 = IP ok (แค่ไม่มี auth)
  - server ตอบ 403      = IP ban (บล็อก ASN/geo)
  - server ตอบ 5xx/ไม่ตอบ = เน็ตมีปัญหา / tunnel ตัด

ใช้:
  python ip_check.py
  python ip_check.py --proxy socks5h://127.0.0.1:1080
  python ip_check.py --via 10.64.0.1       # เช็คว่า route ผ่าน Mullvad DNS
  python ip_check.py --loop 30 --n 20      # เทสทุก 30s รวม 20 ครั้ง
"""
import argparse, os, sys, time, json

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

BASE = "https://rangers-api.line-apps.com/v12.3"
IPIFY = "https://api.ipify.org"


def check_myip(proxy=None):
    s = requests.Session()
    s.trust_env = False
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    try:
        r = s.get(IPIFY, timeout=8)
        return r.text.strip() if r.ok else f"(ipify {r.status_code})"
    except Exception as e:
        return f"(fail: {type(e).__name__})"


def check_lgr(proxy=None, path="/home"):
    """ยิง rangers-api ไม่ใส่ cookie. คืน (status, note)"""
    s = requests.Session()
    s.trust_env = False
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    headers = {
        "App-Version": "LGRGS/12.3.1;android/12",
        "Nation-Code": "TH",
        "Accept-Language": "en",
        "User-Agent": "LGRGS/12.3.1 (Linux; U; Android 12; en-US; SM-A528B Build/V417IR)",
        "useLGC": "true",
        "X-LINEGAME-MCC": "000",
        "X-LINEGAME-MNC": "00",
        "Accept-Encoding": "identity",
        "X-LINEGAME-TIMESTAMP": str(int(time.time() * 1000)),
    }
    try:
        t0 = time.time()
        r = s.get(BASE + path, headers=headers, timeout=15)
        dt = (time.time() - t0) * 1000
        return r.status_code, f"{dt:.0f}ms"
    except requests.exceptions.ConnectTimeout:
        return 0, "connect timeout"
    except requests.exceptions.ReadTimeout:
        return 0, "read timeout"
    except requests.exceptions.ConnectionError as e:
        return -1, f"conn err: {type(e.__cause__ or e).__name__}"
    except Exception as e:
        return -2, f"{type(e).__name__}: {e}"


def verdict(status):
    if status in (401, 409):
        return "OK", "IP ผ่าน (server reject แค่เพราะไม่มี cookie)"
    if status == 200:
        return "OK+", "IP ผ่าน (รับ anonymous ได้)"
    if status == 403:
        return "BANNED", "IP โดนบล็อก (ASN/geo blacklist)"
    if status == 429:
        return "RATE", "โดน rate-limit (ยิงเยอะไป)"
    if 500 <= status < 600:
        return "SERVER", f"server error {status}"
    if status == 0:
        return "TIMEOUT", "network timeout"
    if status < 0:
        return "NET", "network error"
    return f"HTTP {status}", "แปลก - ดู response"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default=os.environ.get("LGR_PROXY", "").strip() or None,
                    help="SOCKS/HTTP proxy เช่น socks5h://127.0.0.1:1080")
    ap.add_argument("--path", default="/home", help="endpoint ที่จะยิง (default /home)")
    ap.add_argument("--loop", type=float, default=0, help="วินาทีต่อครั้ง (0 = ยิงครั้งเดียว)")
    ap.add_argument("--n", type=int, default=1, help="จำนวนครั้งที่ loop")
    args = ap.parse_args()

    if args.proxy:
        print(f"[CFG] proxy = {args.proxy}")

    myip = check_myip(args.proxy)
    print(f"[IP ] {myip}")

    stats = {"OK": 0, "OK+": 0, "BANNED": 0, "RATE": 0, "SERVER": 0,
             "TIMEOUT": 0, "NET": 0, "OTHER": 0}
    for i in range(args.n if args.loop > 0 else 1):
        status, note = check_lgr(args.proxy, args.path)
        tag, msg = verdict(status)
        print(f"[{i+1:02d}] status={status:4d}  {tag:7s}  {note:18s}  {msg}")
        stats[tag if tag in stats else "OTHER"] = stats.get(tag if tag in stats else "OTHER", 0) + 1
        if args.loop > 0 and i < args.n - 1:
            time.sleep(args.loop)

    if args.n > 1:
        print()
        print("== สรุป ==")
        for k, v in stats.items():
            if v:
                print(f"  {k:8s} {v:3d}/{args.n}  ({100*v/args.n:.1f}%)")


if __name__ == "__main__":
    main()
