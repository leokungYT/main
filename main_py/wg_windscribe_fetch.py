"""wg_windscribe_fetch.py - semi-auto Windscribe .conf fetcher

Windscribe locked down their API behind desktop-app OAuth (Nov 2026 check):
  - api.windscribe.com/Session -> 403 'Missing client authentication values'
  - windscribe.com switched to Next.js SPA, no scrapable endpoints
Reverse-engineering their web/desktop client creds would break at any update.

This script takes the pragmatic path:
  1. Opens https://windscribe.com/getconfig/wireguard in the default browser
  2. Watches the user's Downloads folder for new .conf files
  3. As each .conf lands -> auto-moves it to wg/ip-chan/main-N/keyN.conf

User clicks "Generate + Download" 3 times in the browser (different countries),
the script picks the files up, done.

Run:
  python wg_windscribe_fetch.py            # waits for 3 configs, timeout 10 min
  python wg_windscribe_fetch.py --count 5  # wait for 5 configs

After success -> rotator will regenerate pool of 30 fresh configs from the new keypairs.
"""
import argparse
import glob
import os
import shutil
import sys
import time
import webbrowser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


def _dst_dir(i):
    """main-1, main-2, ... main-N (ไม่จำกัด - รองรับ Pro 5 keypairs ด้วย)"""
    return os.path.join(SCRIPT_DIR, "wg", "ip-chan", f"main-{i}")


GETCONFIG_URL = "https://windscribe.com/getconfig/wireguard"


def _snapshot_downloads():
    return set(glob.glob(os.path.join(DOWNLOADS, "*.conf")))


def _valid_wg_conf(path):
    """ตรวจว่าเป็นไฟล์ WG จริง - มี PrivateKey + PublicKey + Endpoint"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            t = f.read()
        return ("PrivateKey" in t and "PublicKey" in t and "Endpoint" in t
                and "[Interface]" in t and "[Peer]" in t)
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Windscribe .conf auto-import")
    ap.add_argument("--count", type=int, default=5, help="จำนวน .conf ที่รอ (default 5 = ใช้ Windscribe Pro 5 keypairs)")
    ap.add_argument("--timeout", type=int, default=600, help="หมดเวลารอ (วินาที, default 600)")
    ap.add_argument("--downloads", default=DOWNLOADS, help=f"โฟลเดอร์ Downloads (default: {DOWNLOADS})")
    args = ap.parse_args()

    if not os.path.isdir(args.downloads):
        print(f"[WS] ไม่พบโฟลเดอร์ Downloads: {args.downloads}")
        sys.exit(1)

    for i in range(1, args.count + 1):
        os.makedirs(_dst_dir(i), exist_ok=True)

    print(f"[WS] =============================================================")
    print(f"[WS] Windscribe Config Fetcher")
    print(f"[WS] =============================================================")
    print(f"[WS] ขั้นตอน:")
    print(f"[WS]   1. เบราว์เซอร์จะเปิดหน้า {GETCONFIG_URL}")
    print(f"[WS]   2. Login ถ้ายังไม่ login")
    print(f"[WS]   3. เลือก Location (แนะนำ: Hong Kong, Singapore, Tokyo)")
    print(f"[WS]   4. กด Generate + Download ไฟล์")
    print(f"[WS]   5. ทำซ้ำ {args.count} ครั้ง (ประเทศต่างกัน)")
    print(f"[WS]")
    print(f"[WS] script จะคอยดูในโฟลเดอร์: {args.downloads}")
    print(f"[WS] ไฟล์ .conf ที่โหลดมาจะย้ายไป wg/ip-chan/main-N/keyN.conf อัตโนมัติ")
    print(f"[WS] =============================================================\n")

    before = _snapshot_downloads()
    print(f"[WS] ตอนนี้มี .conf ใน Downloads อยู่ {len(before)} ไฟล์ - จะไม่สนใจของเก่า")

    try:
        webbrowser.open(GETCONFIG_URL)
        print(f"[WS] เปิดเว็บแล้ว - รอคุณกด Generate + Download...")
    except Exception as e:
        print(f"[WS] เปิดเว็บไม่สำเร็จ ({e}) - เข้าเองที่ {GETCONFIG_URL}")

    collected = []
    deadline = time.time() + args.timeout
    while len(collected) < args.count and time.time() < deadline:
        time.sleep(2)
        cur = _snapshot_downloads()
        new = sorted(cur - before - set(collected), key=lambda p: os.path.getmtime(p))
        for p in new:
            if not _valid_wg_conf(p):
                continue
            idx = len(collected) + 1
            dst = os.path.join(_dst_dir(idx), f"key{idx}.conf")
            try:
                shutil.move(p, dst)
                collected.append(dst)
                remain = args.count - len(collected)
                print(f"[WS] + key{idx}.conf -> {dst}  ({'เสร็จ' if remain == 0 else f'อีก {remain} ไฟล์'})")
            except Exception as e:
                print(f"[WS] ย้ายไม่ได้ ({p}): {e}")
        if len(collected) < args.count:
            remain = args.count - len(collected)
            if int(time.time()) % 30 == 0:
                print(f"[WS] ... รออีก {remain} ไฟล์ ({int(deadline - time.time())}s เหลือ)")

    if len(collected) < args.count:
        print(f"\n[WS] หมดเวลา - ได้ {len(collected)}/{args.count} ไฟล์ - ลองรันใหม่หรือดาวน์โหลดเพิ่ม")
        sys.exit(1)

    print(f"\n[WS] ได้ {len(collected)} ไฟล์ครบแล้ว ✓")
    for c in collected:
        print(f"[WS]   {c}")
    print(f"\n[WS] ต่อไป: รัน host-wg-reset.bat เพื่อเคลียร์ pool เก่า + host-wg-rotate.bat")


if __name__ == "__main__":
    main()
