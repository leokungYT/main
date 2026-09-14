#!/usr/bin/env python3
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

from lgr_api import LGRClient, parse_ruby, parse_coin, parse_tickets

try:
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
except Exception:
    pass

CREDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def _load_creds():
    if not os.path.exists(CREDS):
        print(f"[X] ไม่พบ {CREDS}")
        print("    ต้องจับ credential ก่อน 1 รอบด้วย capture_credential.py (MITM)")
        sys.exit(1)
    try:
        content = open(CREDS, encoding="utf-8").read().strip()
        if not content:
            print(f"[!] {CREDS} ว่างอยู่ (ยังไม่มีบัญชีที่บันทึกไว้)")
            return {}
        return json.loads(content)
    except Exception as e:
        print(f"[!] ไม่สามารถอ่าน {CREDS}: {e}")
        return {}


def login_one(key, cred):
    """ล็อกอิน 1 บัญชี -> คืน dict ผล + LF_AC ที่หมุนใหม่"""
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    if not (udid and lf):
        return {"ok": False, "err": "ไม่มี udid/LF_AC ใน creds.json"}

    c = LGRClient(udid, lf)

    # 1) ลองด้วย session ปัจจุบัน
    st, home = c.home()

    # 2) ถ้า session หมดอายุ -> ขอใหม่ด้วย guestCookie แล้วลองอีกครั้ง
    if st == 401:
        gc = cred.get("guestCookie")
        if not gc:
            return {"ok": False, "err": "LF_AC หมดอายุ และไม่มี guestCookie ให้ /login ใหม่"}
        c.login(gc)
        st, home = c.home()

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
        "ticket": parse_tickets(result, player),     # ตั๋วกาชา (best-effort scan)
        "gift_badge": badge.get("GIFT", 0),
        "lf_ac_next": c.lf_ac,   # เก็บไว้ใช้รอบหน้า (เซิร์ฟหมุนค่าแล้ว)
    }


def main():
    creds = _load_creds()
    if not creds:
        return

    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target not in creds:
            print(f"[X] ไม่พบ id '{target}' ใน creds.json (มี: {', '.join(creds) or '-'})")
            sys.exit(1)
        creds = {target: creds[target]}

    changed = False
    for key, cred in creds.items():
        res = login_one(key, cred)
        if res.get("ok"):
            # เก็บ LF_AC ที่หมุนใหม่กลับ
            cred["LF_AC"] = res.pop("lf_ac_next")
            cred["ruby"] = res.get("ruby")
            cred["coin"] = res.get("coin")
            cred["ticket"] = res.get("ticket")
            cred["level"] = res.get("level")
            changed = True
            fname = res.get("file") or cred.get("file")
            file_str = f" | file={fname}" if fname and fname != "-" else ""
            print(f"[OK ] {key}{file_str}: Lv {res.get('level')} | ruby={res.get('ruby')} "
                  f"coin={res.get('coin')} ticket={res.get('ticket')} gift={res.get('gift_badge')}")
        else:
            print(f"[ERR] {key}: {res}")

    if changed:
        json.dump(creds, open(CREDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
