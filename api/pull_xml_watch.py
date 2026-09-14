#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_xml_watch.py — เฝ้าอีมูฯ แล้ว "ดึง _LINE_COCOS_PREF_KEY.xml ของทุกบัญชีที่บอทสร้าง"
มาเก็บไว้ในเครื่องอัตโนมัติ (ใช้เอง). ดึงตอนบัญชีนั้นยังโหลดอยู่ (ก่อนบอท wipe รอบถัดไป)

หลักการ: poll ค่า _DEVICE_UUID_KEY ใน shared_prefs ทุก ~1 วิ; พอเปลี่ยน (บัญชีใหม่)
         -> cp เป็นไฟล์ temp -> chmod -> adb pull มาเก็บ xml_pool/
         ตั้งชื่อด้วย rsn (ถ้าหาใน creds.json เจอ) ไม่งั้นใช้ udid

ใช้:
  python pull_xml_watch.py                       # auto-detect เครื่อง MuMu (127.0.0.1:*)
  python pull_xml_watch.py --device 127.0.0.1:16416
  python pull_xml_watch.py --interval 1 --out xml_pool

หมายเหตุ: เครื่องต้อง root (su หรือ root adbd). รันคู่กับบอท reroll + MITM capture
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CREDS = os.path.join(HERE, "creds.json")
PKG = "com.linecorp.LGRGS"
PREF = f"/data/data/{PKG}/shared_prefs/_LINE_COCOS_PREF_KEY.xml"


def find_adb():
    for c in (os.path.join(ROOT, "adb", "adb.exe"), os.path.join(ROOT, "adb", "adb"), "adb"):
        if c == "adb" or os.path.exists(c):
            return c
    return "adb"


ADB = find_adb()


def adb(dev, args, timeout=20):
    return subprocess.run([ADB, "-s", dev, *args], capture_output=True, text=True, timeout=timeout)


def detect_device():
    out = subprocess.run([ADB, "devices"], capture_output=True, text=True).stdout.splitlines()
    devs = [l.split()[0] for l in out[1:] if l.strip().endswith("device")]
    mumu = [d for d in devs if d.startswith("127.0.0.1:")]
    if mumu:
        return mumu[0]
    if devs:
        return devs[0]
    sys.exit("[X] ไม่พบเครื่อง adb")


def shell_root(dev, cmd, timeout=20):
    """รัน shell แบบ root: ลอง root adbd ก่อน ไม่ได้ค่อย su"""
    r = adb(dev, ["shell", cmd], timeout=timeout)
    if r.returncode == 0 and "Permission denied" not in (r.stdout + r.stderr):
        return r
    return adb(dev, ["shell", f"su -c '{cmd}'"], timeout=timeout)


def read_current_udid(dev):
    r = shell_root(dev, f"cat {PREF}")
    m = re.search(r'_DEVICE_UUID_KEY">([^<]+)<', r.stdout or "")
    return m.group(1).strip() if m else None


def rsn_for_udid(udid):
    try:
        creds = json.load(open(CREDS, encoding="utf-8"))
        for k, v in creds.items():
            if v.get("udid") == udid:
                return k
    except Exception:
        pass
    return None


def pull_xml(dev, udid, out_dir):
    # tmp แยกตามเครื่อง (กันชนเวลารันหลายอีมูฯ) — แบบเดียวกับ login.py
    tmp = f"/data/local/tmp/temp_pref_{dev.replace(':', '_')}.xml"
    shell_root(dev, f"cp {PREF} {tmp} && chmod 644 {tmp}")
    rsn = rsn_for_udid(udid)
    name = f"pull+[{rsn or udid[:12]}]+_LINE_COCOS_PREF_KEY.xml"
    dst = os.path.join(out_dir, name)
    r = adb(dev, ["pull", tmp, dst], timeout=30)
    shell_root(dev, f"rm -f {tmp}")
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 100:
        # กันไฟล์ซ้ำ/ว่าง: ต้องมี _ENC_LF_AC_KEY จริงถึงถือว่าใช้ได้
        try:
            if "_ENC_LF_AC_KEY" in open(dst, encoding="utf-8", errors="ignore").read():
                return dst
        except Exception:
            return dst
    return None


def main():
    ap = argparse.ArgumentParser(description="เฝ้าดึง .xml ทุกบัญชีที่บอทสร้าง")
    ap.add_argument("--device", help="serial (ไม่ใส่ = auto-detect MuMu)")
    ap.add_argument("--out", default="xml_pool", help="โฟลเดอร์เก็บ .xml (default: xml_pool)")
    ap.add_argument("--interval", type=float, default=1.0, help="poll ทุกกี่วิ (default 1)")
    args = ap.parse_args()

    dev = args.device or detect_device()
    out_dir = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)
    print(f"[*] เฝ้า {dev} -> เก็บ .xml ลง {out_dir} (poll {args.interval}s)  Ctrl+C เพื่อหยุด")

    seen = set()
    saved = 0
    last = None
    while True:
        try:
            udid = read_current_udid(dev)
            if udid and udid != last and udid not in seen:
                dst = pull_xml(dev, udid, out_dir)
                if dst:
                    seen.add(udid)
                    saved += 1
                    print(f"[+{saved}] {os.path.basename(dst)}  (udid={udid[:8]}..)")
                last = udid
            elif udid:
                last = udid
        except Exception as e:
            print(f"[!] {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
