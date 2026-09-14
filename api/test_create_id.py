#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_create_id.py — เช็คบัญชีที่จับได้ (creds.json) ว่า "สุ่มได้ตัวเป้า" ไหม แล้วเซฟออก

หลักการ (สำคัญ — อ่านก่อน):
  * เรา "mint id ใหม่ผ่าน API ตรง ๆ ไม่ได้" (GET /login ด้วย udid สด = 401; guestCookie
    ต้องผ่าน LINE Trident handshake คนละ host) -> ให้ "บอ/เกม" สร้าง guest แล้ว MITM
    (capture_credential.py) เก็บ udid+LF_AC+guestCookie ลง creds.json ให้อัตโนมัติ
  * ไฟล์นี้ทำหน้าที่ "เช็ค + คัดเก็บ": วนบัญชีใน creds.json -> ยิง /home ผ่าน API ->
    ดู unitCode ในทีม -> ถ้ามีตัวเป้า (เช่น kappa) -> เซฟ credential ลงโฟลเดอร์ test_api/
  * .xml (shared_prefs) ประกอบเองไม่ได้ (คีย์เข้ารหัสผูกเครื่อง) -> เซฟเป็น creds JSON แทน
    (ใช้ยิง API ได้เต็ม); ถ้าต้องการ .xml จริงต้อง pull จากเครื่องตอนบัญชีนั้นโหลดอยู่

ใช้:
  python test_create_id.py                 # เช็คทุกบัญชี, target = kappa (ดีฟอลต์)
  python test_create_id.py --id 30bb89e4   # เช็คบัญชีเดียว
  python test_create_id.py --targets kappa,som,kafka
  python test_create_id.py --watch         # เฝ้า creds.json เช็คบัญชีใหม่เรื่อย ๆ (บอทรันคู่)
"""
import argparse
import json
import os
import subprocess
import time

from lgr_api import (
    LGRClient,
    parse_ruby,
    parse_coin,
    parse_tickets,
    load_creds as _api_load_creds,
    save_creds as _api_save_creds,
    merge_part_creds,
    CREDS_FILE,
)

try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CREDS = CREDS_FILE
OUT_DIR = os.path.join(ROOT, "test_api")          # โฟลเดอร์เก็บบัญชีที่ได้ตัวเป้า
CFG = os.path.join(ROOT, "configmain.json")
PKG = "com.linecorp.LGRGS"
PREF = f"/data/data/{PKG}/shared_prefs/_LINE_COCOS_PREF_KEY.xml"


def find_adb():
    for c in (os.path.join(ROOT, "adb", "adb.exe"), os.path.join(ROOT, "adb", "adb"), "adb"):
        if c == "adb" or os.path.exists(c):
            return c
    return "adb"


ADB = find_adb()


def pull_current_xml(device, dest):
    """ดึง _LINE_COCOS_PREF_KEY.xml ของบัญชีที่โหลดอยู่ในเครื่อง -> dest (.xml จริง inject กลับได้)
       รองรับ root adbd และ su. คืน path หรือ None"""
    tmp = "/data/local/tmp/_hit_pref.xml"
    # ลองแบบ root adbd ก่อน, ไม่ได้ค่อย su
    cmds = [
        f'cp {PREF} {tmp} && chmod 644 {tmp}',
        f"su -c 'cp {PREF} {tmp} && chmod 644 {tmp}'",
    ]
    for cmd in cmds:
        subprocess.run([ADB, "-s", device, "shell", cmd], capture_output=True, text=True, timeout=20)
        r = subprocess.run([ADB, "-s", device, "pull", tmp, dest], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 100:
            subprocess.run([ADB, "-s", device, "shell", f"rm -f {tmp}"], capture_output=True)
            return dest
    return None


def device_current_udid(device):
    """อ่าน _DEVICE_UUID_KEY ของบัญชีที่โหลดอยู่ (จาก shared_prefs) โดยไม่ต้อง pull ไฟล์"""
    for cmd in (f'cat {PREF}', f"su -c 'cat {PREF}'"):
        r = subprocess.run([ADB, "-s", device, "shell", cmd], capture_output=True, text=True, timeout=15)
        import re
        m = re.search(r'_DEVICE_UUID_KEY">([^<]+)<', r.stdout or "")
        if m:
            return m.group(1).strip()
    return None


def load_creds():
    return _api_load_creds(CREDS, auto_merge=True)


def default_targets():
    """ดึงชื่อฮีโร่เป้าจาก configmain.json (HERO_MAPPING) -> substring ตัวเล็ก"""
    subs = set()
    try:
        cfg = json.load(open(CFG, encoding="utf-8"))
        for name in (cfg.get("HERO_MAPPING", {}) or {}).values():
            s = name.lower().replace("+", "").replace("u", "").strip()
            if s:
                subs.add(s)
    except Exception:
        pass
    subs.add("kappa")
    return sorted(subs)


def account_unit_codes(cli):
    """คืน (st, codes, home) จาก /home"""
    st, home = cli.home()
    codes = set()
    if st != 200 or not isinstance(home, dict):
        return st, codes, home
    teams = home.get("result", {}).get("playerUnitTeams", {}) or {}
    for team in teams.values():
        for slot in team or []:
            uc = slot.get("unitCode")
            if uc:
                codes.add(uc)
    return st, codes, home


def check_account(key, cred, targets):
    """คืน (ok, hits, codes, info)"""
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    if not (udid and lf):
        return False, [], set(), {}
    cli = LGRClient(udid, lf)
    st, codes, home = account_unit_codes(cli)
    if st == 401 and cred.get("guestCookie"):
        cli.login(cred["guestCookie"])
        st, codes, home = account_unit_codes(cli)
    cred["LF_AC"] = cli.lf_ac   # เก็บ LF_AC ที่หมุนใหม่

    info = {
        "file": cred.get("file", "-"),
        "ruby": cred.get("ruby", 0),
        "ticket": cred.get("ticket", 0),
        "coin": cred.get("coin", 0),
        "level": cred.get("level", 1),
    }

    if isinstance(home, dict) and "result" in home:
        res = home["result"]
        player = res.get("player") or {}
        r_ruby = parse_ruby(res, player)
        r_coin = parse_coin(res, player)
        r_ticket = parse_tickets(res, player)
        if r_ruby: info["ruby"] = r_ruby
        if r_coin: info["coin"] = r_coin
        if r_ticket: info["ticket"] = r_ticket
        if player.get("level"): info["level"] = player["level"]
        # อัปเดตกลับเข้า cred ด้วย
        cred["ruby"] = info["ruby"]
        cred["coin"] = info["coin"]
        cred["ticket"] = info["ticket"]
        cred["level"] = info["level"]

    if st != 200:
        return False, [], codes, info
    hits = [t for t in targets if any(t in c.lower() for c in codes)]
    return True, hits, codes, info


def save_hit(key, cred, hits, codes, info, device=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"api+[{key}]+creds.json")
    data = {
        "rsn": key,
        "file": info.get("file") or cred.get("file"),
        "ruby": info.get("ruby", 0),
        "ticket": info.get("ticket", 0),
        "coin": info.get("coin", 0),
        "level": info.get("level", 1),
        "udid": cred.get("udid"),
        "LF_AC": cred.get("LF_AC"),
        "guestCookie": cred.get("guestCookie"),
        "hit_targets": hits,
        "unit_codes": sorted(codes),
        "saved_at": int(time.time()),
    }
    json.dump(data, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # ถ้าระบุ device และบัญชีนี้คือบัญชีที่โหลดอยู่ -> pull .xml จริงด้วย
    if device:
        cur = device_current_udid(device)
        if cur and cur == cred.get("udid"):
            xml_dst = os.path.join(OUT_DIR, f"api+[{key}]+_LINE_COCOS_PREF_KEY.xml")
            if pull_current_xml(device, xml_dst):
                print(f"       + pull .xml จริงได้: {os.path.basename(xml_dst)}")
        else:
            print(f"       (บัญชีนี้ไม่ได้โหลดอยู่ในเครื่อง -> เซฟแค่ creds)")
    return dst


def run_once(target_id, targets, device=None):
    creds = load_creds()
    if not creds:
        print(f"[!] ไม่พบบัญชีใน {CREDS} (และไม่พบไฟล์ creds.part*.json)")
        print("    ยังไม่มี credential บันทึกอยู่ในระบบ")
        return 0
    if target_id:
        creds = {k: v for k, v in creds.items() if k == target_id}
    hits_total = 0
    for key, cred in creds.items():
        ok, hits, codes, info = check_account(key, cred, targets)
        fname = info.get("file") or cred.get("file") or "-"
        ruby = info.get("ruby", cred.get("ruby", 0))
        ticket = info.get("ticket", cred.get("ticket", 0))
        if not ok:
            print(f"[skip] {key} | file={fname}: เช็คไม่ได้ (401/ไม่มี cred)")
            continue
        if hits:
            dst = save_hit(key, cred, hits, codes, info, device)
            hits_total += 1
            print(f"[HIT!] {key} | file={fname} | ruby={ruby} | ticket={ticket} ได้ {hits} -> เซฟ {os.path.basename(dst)}")
        else:
            print(f"[miss] {key} | file={fname} | ruby={ruby} | ticket={ticket}: {sorted(codes)}")
    # เซฟ LF_AC และ resource ที่หมุนกลับ creds.json
    allc = load_creds()
    for k, v in creds.items():
        if k in allc:
            allc[k].update(v)
    _api_save_creds(allc, CREDS)
    return hits_total


def main():
    ap = argparse.ArgumentParser(description="เช็คบัญชีที่จับได้ว่าได้ตัวเป้าไหม -> เซฟ test_api/")
    ap.add_argument("--id", help="เช็คเฉพาะ rsn นี้ (ไม่ใส่ = ทุกบัญชี)")
    ap.add_argument("--targets", help="ชื่อตัวเป้า คั่นด้วย , (ไม่ใส่ = จาก configmain.json + kappa)")
    ap.add_argument("--watch", action="store_true", help="เฝ้า creds.json เช็คบัญชีใหม่เรื่อย ๆ")
    ap.add_argument("--device", help="serial อีมูฯ (เช่น 127.0.0.1:16416) — ถ้า HIT + บัญชีโหลดอยู่ จะ pull .xml จริงด้วย")
    ap.add_argument("--dump-xml", metavar="SERIAL", help="แค่ pull .xml ของบัญชีที่โหลดอยู่ในเครื่องนี้ -> test_api/ (ทดสอบ)")
    args = ap.parse_args()

    if args.dump_xml:
        os.makedirs(OUT_DIR, exist_ok=True)
        udid = device_current_udid(args.dump_xml) or "unknown"
        dst = os.path.join(OUT_DIR, f"dump+[{udid[:8]}]+_LINE_COCOS_PREF_KEY.xml")
        p = pull_current_xml(args.dump_xml, dst)
        print(f"pull .xml -> {p or 'FAIL'} (udid={udid})")
        return

    targets = [t.strip().lower() for t in args.targets.split(",")] if args.targets else default_targets()
    print(f"[*] target units (substring): {targets}")
    print(f"[*] เซฟบัญชีที่ HIT ลง: {OUT_DIR}")

    if not args.watch:
        n = run_once(args.id, targets, args.device)
        print(f"\n[DONE] HIT รวม {n} บัญชี")
        return

    seen = set()
    print("[*] watch mode — เปิดบอทสร้าง+สุ่มคู่กันได้เลย (Ctrl+C เพื่อหยุด)")
    while True:
        for key, cred in load_creds().items():
            if key in seen:
                continue
            seen.add(key)
            ok, hits, codes, info = check_account(key, cred, targets)
            fname = info.get("file") or cred.get("file") or "-"
            ruby = info.get("ruby", cred.get("ruby", 0))
            ticket = info.get("ticket", cred.get("ticket", 0))
            if ok and hits:
                dst = save_hit(key, cred, hits, codes, info, args.device)
                print(f"[HIT!] {key} | file={fname} | ruby={ruby} | ticket={ticket} ได้ {hits} -> {os.path.basename(dst)}")
            elif ok:
                print(f"[miss] {key} | file={fname} | ruby={ruby} | ticket={ticket}")
        time.sleep(10)


if __name__ == "__main__":
    main()
