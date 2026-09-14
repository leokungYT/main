#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_team.py — ตรวจสอบทีม / ตัวละคร (Rangers) ของทุกบัญชีใน creds.json ผ่าน API ตรง
เช็คว่ามีตัวเป้าหมาย (เช่น kappa, som, kafka, kikoru) ตาม configmain.json หรือไม่
และเซฟบัญชีที่ได้ตัวเป้า (HIT) ออกไปยังโฟลเดอร์ test_api/ อัตโนมัติ

หลักการ:
  * ดึงเป้าหมายอัตโนมัติจาก configmain.json (HERO_MAPPING, Hero_low) หรือกำหนดเองผ่าน --targets
  * ยิง /home ผ่าน API ตรง ดึงข้อมูล playerUnitTeams และตัวละครทั้งหมดในบัญชี
  * หาก session ไม่ผ่าน (เช่น 400 หรือ 401) ระบบจะนำ guestCookie ไปขอ session ใหม่ (/login) ให้อัตโนมัติ
  * หากพบบัญชีที่มีตัวเป้าหมาย (HIT) จะบันทึก credential ลง test_api/api+[<key>]+creds.json
  * รองรับการรันแบบขนานหลายบัญชีพร้อมกัน (Multi-threading) รวดเร็ว ตรวจสอบเสร็จในไม่กี่วินาที

ใช้:
  python check_team.py                     # ตรวจสอบทุกบัญชี (เป้าหมายจาก configmain.json)
  python check_team.py --targets kappa,som # กำหนดชื่อตัวเป้าเอง
  python check_team.py --id 30bb89e4       # ตรวจสอบเฉพาะบัญชีเดียว
  python check_team.py --only-hits         # แสดงเฉพาะบัญชีที่ได้ตัวเป้า (HIT)
  python check_team.py --watch             # เฝ้า creds.json ตรวจสอบบัญชีใหม่อัตโนมัติ
  python check_team.py --device 127.0.0.1:16416  # ถ้า HIT + โหลดอยู่ในเครื่อง จะ pull .xml ให้ด้วย
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            msg = " ".join(str(a) for a in args)
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(msg.encode(enc, errors="replace").decode(enc), **kwargs)
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
    """ดึง _LINE_COCOS_PREF_KEY.xml ของบัญชีที่โหลดอยู่ในเครื่อง -> dest (.xml จริง inject กลับได้)"""
    tmp = "/data/local/tmp/_hit_pref.xml"
    cmds = [
        f'cp {PREF} {tmp} && chmod 644 {tmp}',
        f"su -c 'cp {PREF} {tmp} && chmod 644 {tmp}'",
    ]
    for cmd in cmds:
        try:
            subprocess.run([ADB, "-s", device, "shell", cmd], capture_output=True, text=True, timeout=20)
            r = subprocess.run([ADB, "-s", device, "pull", tmp, dest], capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 100:
                subprocess.run([ADB, "-s", device, "shell", f"rm -f {tmp}"], capture_output=True)
                return dest
        except Exception:
            pass
    return None


def device_current_udid(device):
    """อ่าน _DEVICE_UUID_KEY ของบัญชีที่โหลดอยู่ (จาก shared_prefs) โดยไม่ต้อง pull ไฟล์"""
    for cmd in (f'cat {PREF}', f"su -c 'cat {PREF}'"):
        try:
            r = subprocess.run([ADB, "-s", device, "shell", cmd], capture_output=True, text=True, timeout=15)
            m = re.search(r'_DEVICE_UUID_KEY">([^<]+)<', r.stdout or "")
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    return None


def load_creds():
    return _api_load_creds(CREDS, auto_merge=True)


def default_targets():
    """ดึงชื่อฮีโร่เป้าจาก configmain.json (HERO_MAPPING + Hero_low)"""
    targets = set()
    try:
        if os.path.exists(CFG):
            cfg = json.load(open(CFG, encoding="utf-8"))
            # 1. HERO_MAPPING
            for name in (cfg.get("HERO_MAPPING", {}) or {}).values():
                s = re.sub(r'U\+?$|\+$', '', name).strip().lower()
                if s:
                    targets.add(s)
            # 2. Hero_low
            hero_low = cfg.get("Hero_low", {}) or {}
            for item in hero_low.values():
                if isinstance(item, dict) and "name" in item:
                    s = re.sub(r'U\+?$|\+$', '', item["name"]).strip().lower()
                    if s:
                        targets.add(s)
    except Exception:
        pass
    if not targets:
        targets.update(["kappa", "som", "kafka", "kikoru"])
    return sorted(targets)


def account_units_info(cli):
    """
    ดึงข้อมูลทีมและตัวละครทั้งหมดในบัญชี
    คืน (status, list_of_unit_codes, team_slots_display, raw_home)
    """
    st, home = cli.home()
    if st != 200 or not isinstance(home, dict):
        return st, [], [], home

    res = home.get("result", {}) or {}
    codes = []
    seen = set()
    team_slots = []

    # 1. ตรวจสอบ playerUnitTeams (ทีม A/B)
    teams = res.get("playerUnitTeams", {}) or {}
    if isinstance(teams, dict):
        for team_name in sorted(teams.keys()):
            slots = teams[team_name] or []
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                uc = slot.get("unitCode") or slot.get("dataCode") or slot.get("code")
                lv = slot.get("level")
                if uc:
                    if uc not in seen:
                        seen.add(uc)
                        codes.append(uc)
                    display = f"{uc}" + (f"(Lv.{lv})" if lv else "")
                    team_slots.append(display)
    elif isinstance(teams, list):
        for slot in teams:
            if not isinstance(slot, dict):
                continue
            uc = slot.get("unitCode") or slot.get("dataCode") or slot.get("code")
            lv = slot.get("level")
            if uc:
                if uc not in seen:
                    seen.add(uc)
                    codes.append(uc)
                display = f"{uc}" + (f"(Lv.{lv})" if lv else "")
                team_slots.append(display)

    # 2. ตรวจสอบ playerUnits (คลังตัวละคร) ถ้ามี
    units = res.get("playerUnits") or res.get("units") or []
    if isinstance(units, list):
        for u in units:
            if not isinstance(u, dict):
                continue
            uc = u.get("unitCode") or u.get("dataCode") or u.get("code")
            if uc and uc not in seen:
                seen.add(uc)
                codes.append(uc)

    return st, codes, team_slots, home


def match_targets(codes, targets):
    """ตรวจว่าใน unit codes มีชื่อเป้าหมายหรือไม่ (เปรียบเทียบแบบ substring ตัวเล็ก)"""
    hits = []
    for t in targets:
        t_clean = t.lower().strip()
        if not t_clean:
            continue
        for c in codes:
            if t_clean in c.lower():
                if t_clean not in hits:
                    hits.append(t_clean)
                break
    return hits


def save_hit_account(key, cred, hits, codes, info, out_dir=OUT_DIR, device=None):
    """บันทึก credential ของบัญชีที่ HIT ลง test_api/ พร้อม pull .xml ถ้าเครื่องเชื่อมต่ออยู่"""
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"api+[{key}]+creds.json")
    data = {
        "rsn": key,
        "file": info.get("file") or cred.get("file", "-"),
        "ruby": info.get("ruby", 0),
        "ticket": info.get("ticket", 0),
        "coin": info.get("coin", 0),
        "level": info.get("level", 1),
        "udid": cred.get("udid"),
        "LF_AC": cred.get("LF_AC"),
        "guestCookie": cred.get("guestCookie"),
        "hit_targets": hits,
        "unit_codes": codes,
        "saved_at": int(time.time()),
    }
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    xml_saved = None
    if device:
        cur_udid = device_current_udid(device)
        if cur_udid and cur_udid == cred.get("udid"):
            xml_dst = os.path.join(out_dir, f"api+[{key}]+_LINE_COCOS_PREF_KEY.xml")
            if pull_current_xml(device, xml_dst):
                xml_saved = xml_dst

    return dst, xml_saved


def check_one_account(key, cred, targets, out_dir=OUT_DIR, device=None):
    """ตรวจสอบบัญชี 1 บัญชี -> คืน dict ผลลัพธ์"""
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    fname = cred.get("file", "-")
    if not (udid and lf):
        return {
            "key": key,
            "ok": False,
            "file": fname,
            "err": "ไม่มี udid หรือ LF_AC ใน creds.json",
        }

    cli = LGRClient(udid, lf)
    st, codes, team_slots, home = account_units_info(cli)

    # ถ้าไม่ผ่าน (400, 401 หรืออื่นๆ) และมี guestCookie -> ให้ /login เพื่อต่อ session ใหม่ทันที!
    if st != 200 and cred.get("guestCookie"):
        st_l, login_res = cli.login(cred["guestCookie"])
        if st_l == 200:
            st, codes, team_slots, home = account_units_info(cli)

    cred["LF_AC"] = cli.lf_ac   # เก็บ LF_AC ที่หมุนใหม่กลับเข้า cred

    info = {
        "key": key,
        "file": fname,
        "ruby": cred.get("ruby", 0),
        "ticket": cred.get("ticket", 0),
        "coin": cred.get("coin", 0),
        "level": cred.get("level", 1),
        "codes": codes,
        "team": team_slots,
    }

    if isinstance(home, dict) and "result" in home:
        res = home["result"]
        player = res.get("player") or {}
        r_ruby = parse_ruby(res, player)
        r_coin = parse_coin(res, player)
        r_ticket = parse_tickets(res, player)
        if r_ruby is not None: info["ruby"] = r_ruby; cred["ruby"] = r_ruby
        if r_coin is not None: info["coin"] = r_coin; cred["coin"] = r_coin
        if r_ticket is not None: info["ticket"] = r_ticket; cred["ticket"] = r_ticket
        if player.get("level"): info["level"] = player["level"]; cred["level"] = player["level"]

    if st != 200:
        err_msg = ""
        if isinstance(home, dict):
            err_msg = home.get("message") or home.get("errorCode") or str(home)
        else:
            err_msg = str(home)[:100]
        return {
            "key": key,
            "ok": False,
            "file": fname,
            "step": "home",
            "status": st,
            "detail": err_msg,
            "has_gc": bool(cred.get("guestCookie")),
        }

    hits = match_targets(codes, targets)
    info["ok"] = True
    info["hits"] = hits
    info["is_hit"] = len(hits) > 0

    if info["is_hit"]:
        dst, xml_dst = save_hit_account(key, cred, hits, codes, info, out_dir, device)
        info["saved_dst"] = dst
        info["saved_xml"] = xml_dst

    return info


def run_batch(targets, target_id=None, out_dir=OUT_DIR, device=None, only_hits=False, workers=8):
    """รันตรวจสอบบัญชีทั้งหมด (หรือเฉพาะ target_id) แบบขนาน"""
    creds = load_creds()
    if not creds:
        _safe_print(f"[!] ไม่พบบัญชีใน {CREDS} (และไม่พบไฟล์ creds.part*.json)")
        _safe_print("    ยังไม่มี credential บันทึกอยู่ในระบบ")
        _safe_print("    -> แนะนำให้รัน: python capture_auto.py ก่อน เพื่อจับ credential เข้าสู่ระบบ")
        return 0, 0, 0

    items = list(creds.items())
    if target_id:
        if target_id not in creds:
            _safe_print(f"[X] ไม่พบ id '{target_id}' ใน creds.json (มี: {', '.join(creds) or '-'})")
            return 0, 0, 0
        items = [(target_id, creds[target_id])]

    total = len(items)
    _safe_print(f"[*] ตรวจสอบ {total} บัญชี ใน creds.json (เป้าหมาย: {targets})")
    _safe_print("-" * 75)

    hit_count = 0
    miss_count = 0
    err_count = 0
    hit_list = []

    num_workers = min(max(1, workers), total)
    with cf.ThreadPoolExecutor(max_workers=num_workers) as ex:
        futures = {ex.submit(check_one_account, k, v, targets, out_dir, device): k for k, v in items}
        for fut in cf.as_completed(futures):
            res = fut.result()
            key = res.get("key")
            fname = res.get("file", "-")
            file_str = f" | {fname}" if fname and fname != "-" else ""

            if not res.get("ok"):
                err_count += 1
                status = res.get("status", "-")
                detail = res.get("detail", res.get("err", ""))
                _safe_print(f"[ERR ] {key:<10}{file_str} | status {status}: {detail}")
            elif res.get("is_hit"):
                hit_count += 1
                hit_list.append(res)
                hits_str = ", ".join(res.get("hits", []))
                team_str = ", ".join(res.get("team", [])[:5]) or "ว่าง"
                xml_note = " (+XML)" if res.get("saved_xml") else ""
                _safe_print(f"[HIT!] {key:<10}{file_str} | Lv {res.get('level')} | ruby={res.get('ruby')} ticket={res.get('ticket')} | ได้: [{hits_str}] | ทีม: [{team_str}]{xml_note}")
            else:
                miss_count += 1
                if not only_hits:
                    team_str = ", ".join(res.get("team", [])[:5]) or "ว่าง"
                    _safe_print(f"[miss] {key:<10}{file_str} | Lv {res.get('level')} | ruby={res.get('ruby')} ticket={res.get('ticket')} | ทีม: [{team_str}]")

    # เซฟ creds ที่มี LF_AC/ruby/ticket หมุนใหม่กลับลง creds.json
    _api_save_creds(creds, CREDS)

    _safe_print("\n" + "=" * 75)
    _safe_print("สรุปผลการตรวจสอบทีม:")
    _safe_print(f"  - พบบัญชีเป้าหมาย (HIT): {hit_count}/{total} บัญชี -> บันทึกลง {os.path.basename(out_dir)}/")
    _safe_print(f"  - บัญชีทั่วไป (Miss):    {miss_count}/{total} บัญชี")
    _safe_print(f"  - ตรวจสอบไม่ผ่าน (Error): {err_count}/{total} บัญชี")
    if hit_list:
        _safe_print("\nรายชื่อบัญชีที่ได้ตัวเป้า (HIT):")
        for h in hit_list:
            hits_str = ", ".join(h.get("hits", []))
            _safe_print(f"    - {h.get('key'):<10} | ได้: [{hits_str:<15}] | ruby={h.get('ruby')} ticket={h.get('ticket')} | file={h.get('file')}")
    _safe_print("=" * 75)

    return hit_count, miss_count, err_count


def watch_loop(targets, out_dir=OUT_DIR, device=None, only_hits=False, workers=4, interval=8):
    """เฝ้า creds.json ตรวจสอบบัญชีใหม่เรื่อย ๆ แบบ Real-time"""
    _safe_print(f"[*] เริ่มโหมด WATCH เฝ้า creds.json (เป้าหมาย: {targets})")
    _safe_print(f"[*] เช็คทุก {interval} วินาที (กด Ctrl+C เพื่อหยุด)...\n")
    seen_keys = set()
    total_hits = 0

    try:
        while True:
            creds = load_creds()
            new_items = [(k, v) for k, v in creds.items() if k not in seen_keys]
            if new_items:
                for k, v in new_items:
                    seen_keys.add(k)
                    res = check_one_account(k, v, targets, out_dir, device)
                    fname = res.get("file", "-")
                    file_str = f" | {fname}" if fname and fname != "-" else ""
                    if not res.get("ok"):
                        _safe_print(f"[ERR ] {k:<10}{file_str} | status {res.get('status', '-')}: {res.get('detail', '')}")
                    elif res.get("is_hit"):
                        total_hits += 1
                        hits_str = ", ".join(res.get("hits", []))
                        team_str = ", ".join(res.get("team", [])[:5]) or "ว่าง"
                        xml_note = " (+XML)" if res.get("saved_xml") else ""
                        _safe_print(f"[HIT!] {k:<10}{file_str} | Lv {res.get('level')} | ruby={res.get('ruby')} ticket={res.get('ticket')} | ได้: [{hits_str}] | ทีม: [{team_str}]{xml_note}")
                    elif not only_hits:
                        team_str = ", ".join(res.get("team", [])[:5]) or "ว่าง"
                        _safe_print(f"[miss] {k:<10}{file_str} | Lv {res.get('level')} | ruby={res.get('ruby')} ticket={res.get('ticket')} | ทีม: [{team_str}]")
                _api_save_creds(creds, CREDS)
            time.sleep(interval)
    except KeyboardInterrupt:
        _safe_print(f"\n[*] หยุดการเฝ้าแล้ว | พบตัวเป้าหมายทั้งหมด {total_hits} บัญชี")


def main():
    ap = argparse.ArgumentParser(
        description="check_team.py — ตรวจสอบทีม/ตัวละครทุกบัญชีใน creds.json ว่าได้ตัวเป้าหมายหรือไม่"
    )
    ap.add_argument("--id", help="เช็คเฉพาะ rsn/ID นี้ (ถ้าไม่ใส่ = ทุกบัญชี)")
    ap.add_argument("--targets", help="ชื่อตัวเป้า คั่นด้วยจุลภาค เช่น kappa,som,kafka (ถ้าไม่ใส่ = จาก configmain.json)")
    ap.add_argument("--only-hits", action="store_true", help="แสดงผลเฉพาะบัญชีที่ได้ตัวเป้า (HIT)")
    ap.add_argument("--out-dir", default=OUT_DIR, help=f"โฟลเดอร์สำหรับเซฟบัญชีที่ HIT (ดีฟอลต์: {OUT_DIR})")
    ap.add_argument("--workers", type=int, default=8, help="จำนวน thread ขนานในการตรวจสอบ (ดีฟอลต์: 8)")
    ap.add_argument("--device", help="serial เครื่องอีมูฯ เช่น 127.0.0.1:16416 (ถ้า HIT + บัญชีโหลดอยู่ จะ pull .xml ให้ด้วย)")
    ap.add_argument("--watch", action="store_true", help="โหมดเฝ้า creds.json ตรวจสอบบัญชีใหม่อัตโนมัติ")
    ap.add_argument("--interval", type=int, default=8, help="ระยะเวลาหน่วงในการวนรอบโหมด watch (วินาที)")
    args = ap.parse_args()

    # วิเคราะห์เป้าหมาย
    if args.targets:
        targets = [t.strip().lower() for t in args.targets.split(",") if t.strip()]
    else:
        targets = default_targets()

    if args.watch:
        watch_loop(targets, args.out_dir, args.device, args.only_hits, args.workers, args.interval)
    else:
        run_batch(targets, args.id, args.out_dir, args.device, args.only_hits, args.workers)


if __name__ == "__main__":
    main()
