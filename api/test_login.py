#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_login.py — เทสเฉพาะ "ล็อกอิน" ผ่าน API ตรง (ไม่เปิดเกม)

หลักการ:
  - auth ใช้ credential (udid + LF_AC/guestCookie) ที่จับไว้ใน creds.json
  - "id" ที่พิมพ์ตอนรัน cmd = คีย์ไปเปิด creds.json (rsn/USER_GAME_ID)  ไม่ใช่ login เอง
  - ลอง /home ด้วย LF_AC ก่อน ถ้า 401 (หมดอายุ) ค่อย /login ด้วย guestCookie
  - สำเร็จ = คืนข้อมูล player + เก็บ LF_AC ที่หมุนใหม่กลับลง creds.json

ใช้:
  python test_login.py            # เทสทุกบัญชีใน creds.json
  python test_login.py 10a86152   # เทสเฉพาะ id เดียว
"""
import json
import os
import sys

from lgr_api import (
    LGRClient,
    parse_ruby,
    parse_coin,
    parse_tickets,
    load_creds,
    save_creds,
    merge_part_creds,
    CREDS_FILE,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
except Exception:
    pass

CREDS = CREDS_FILE


def _load_creds():
    creds = load_creds(CREDS, auto_merge=True)
    if not creds:
        print(f"[!] ไม่พบบัญชีใน {CREDS} (และไม่พบไฟล์ creds.part*.json)")
        print("    ยังไม่มี credential บันทึกอยู่ในระบบ")
        print("    -> แนะนำให้รัน: python capture_auto.py ก่อน เพื่อจับ credential เข้าสู่ระบบ")
        return {}
    return creds


def login_one(key, cred):
    """ล็อกอิน 1 บัญชี -> คืน dict ผล + LF_AC ที่หมุนใหม่"""
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    if not (udid and lf):
        return {"ok": False, "err": "ไม่มี udid/LF_AC ใน creds.json"}

    c = LGRClient(udid, lf)

    # 1) ลองด้วย session ปัจจุบัน
    st, home = c.home()

    # 2) ถ้า session ไม่ผ่าน (400, 401 หรืออื่นๆ) -> ขอใหม่ด้วย guestCookie แล้วลองอีกครั้ง
    if st != 200:
        gc = cred.get("guestCookie")
        if gc:
            st_l, login_res = c.login(gc)
            if st_l == 200:
                st, home = c.home()
            else:
                return {"ok": False, "err": f"/login ด้วย guestCookie ล้มเหลว (status {st_l})", "detail": login_res}
        else:
            return {"ok": False, "err": f"session ไม่ผ่าน (status {st}) และไม่มี guestCookie ใน creds.json", "detail": home}

    if st != 200 or not isinstance(home, dict):
        return {"ok": False, "step": "home", "status": st, "detail": home}

    result = home.get("result", {})
    player = result.get("player", {}) or {}
    badge = result.get("badge", {}) or {}
    return {
        "ok": True,
        "file": cred.get("file", "-"),
        "rsn": player.get("rsn") or result.get("rsn") or key,
        "userName": player.get("userName"),
        "level": player.get("level") or result.get("level"),
        "ruby": parse_ruby(result, player),          # เพชร/รูบี้ (พรีเมียม)
        "coin": parse_coin(result, player),          # เหรียญทอง
        "ticket": c.ticket_count().get("total", 0),  # ตั๋วกาชาจริงจาก /player/item
        "gift_badge": badge.get("GIFT", 0),
        "lf_ac_next": c.lf_ac,   # เก็บไว้ใช้รอบหน้า (เซิร์ฟหมุนค่าแล้ว)
    }


def main():
    creds = _load_creds()
    if not creds:
        return

    # สำคัญ: process เฉพาะบัญชีที่ระบุ แต่ "อย่าทิ้ง" บัญชีอื่นออกจาก creds (เดี๋ยวเขียนทับหาย)
    targets = list(creds.keys())
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target not in creds:
            print(f"[X] ไม่พบ id '{target}' ใน creds.json (มี: {', '.join(creds) or '-'})")
            sys.exit(1)
        targets = [target]

    print(f"[*] พบทั้งหมด {len(targets)} บัญชี ใน creds.json กำลังเริ่มทดสอบล็อกอินผ่าน API...\n", flush=True)
    suc_cnt = 0
    fail_cnt = 0
    changed = False
    for key in targets:
        cred = creds[key]
        res = login_one(key, cred)
        if res.get("ok"):
            suc_cnt += 1
            # เก็บ LF_AC ที่หมุนใหม่กลับ
            cred["LF_AC"] = res.pop("lf_ac_next")
            cred["ruby"] = res.get("ruby")
            cred["coin"] = res.get("coin")
            cred["ticket"] = res.get("ticket")
            cred["level"] = res.get("level")
            changed = True
            fname = res.get("file") or cred.get("file")
            file_str = f" | file={fname}" if fname and fname != "-" else ""
            print(f"[OK ] {key:<10}{file_str}: Lv {res.get('level')} | ruby={res.get('ruby')} "
                  f"coin={res.get('coin')} ticket={res.get('ticket')} gift={res.get('gift_badge')}", flush=True)
        else:
            fail_cnt += 1
            print(f"[ERR] {key:<10}: {res}", flush=True)

    if changed:
        save_creds(creds, CREDS)

    print("\n" + "=" * 55, flush=True)
    print(f"สรุปผลการทดสอบล็อกอิน:", flush=True)
    print(f"  - สำเร็จ: {suc_cnt} บัญชี", flush=True)
    print(f"  - ล้มเหลว: {fail_cnt} บัญชี", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
