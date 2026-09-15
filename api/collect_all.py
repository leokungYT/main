#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
collect_all.py — รับของทุกบัญชีใน creds.json รวดเดียว (ยิง API ตรง ไม่เปิดเกม)
รันขนานหลายบัญชี + เก็บ LF_AC ที่หมุนใหม่กลับลง creds.json ให้อัตโนมัติ

ใช้:  python collect_all.py            # รับของทุกบัญชี
      python collect_all.py 10a86152  # เฉพาะบัญชีเดียว (ใส่ rsn/คีย์)
"""
import json
import os
import sys
import concurrent.futures as cf

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
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
except Exception:
    pass

CREDS = CREDS_FILE


def load_creds():
    return _api_load_creds(CREDS, auto_merge=True)


def _one(key, cred):
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    fname = cred.get("file", "-")
    if not (udid and lf):
        return key, {"ok": False, "file": fname, "err": "no udid/LF_AC"}
    try:
        c = LGRClient(udid, lf)
        st, home = c.home()
        # ถ้า home ไม่ผ่าน (400, 401 หรืออื่นๆ) -> ถ้ามี guestCookie ให้ลอง /login เพื่อขอ session ใหม่ทันที
        if st != 200 and cred.get("guestCookie"):
            st_l, login_res = c.login(cred["guestCookie"])
            if st_l == 200:
                st, home = c.home()

        if st != 200:
            err_msg = ""
            if isinstance(home, dict):
                err_msg = home.get("message") or home.get("errorCode") or home
            else:
                err_msg = str(home)[:120]
            gc_status = "has_gc" if cred.get("guestCookie") else "no_gc"
            return key, {"ok": False, "file": fname, "step": "home", "status": st, "detail": err_msg, "gc": gc_status}
        badge = home.get("result", {}).get("badge", {})
        st_b, un = c.unclaimed_gifts()
        n = len(un or [])
        claimed = 0
        if n > 0:
            c.receive_all_gifts()
            st2, un2 = c.unclaimed_gifts()
            claimed = n - len(un2 or [])
            st_fresh, home_fresh = c.home()
            if st_fresh == 200 and isinstance(home_fresh, dict):
                home = home_fresh

        res = home.get("result", {})
        player = res.get("player") or {}
        ruby = parse_ruby(res, player) or cred.get("ruby", 0)
        coin = parse_coin(res, player) or cred.get("coin", 0)
        tk = c.ticket_count()               # ตั๋วกาชาจริงจาก /player/item (นับหลังรับของแล้ว)
        ticket = tk.get("total", 0)

        return key, {
            "ok": True,
            "file": fname,
            "ruby": ruby,
            "ticket": ticket,
            "coin": coin,
            "gift_badge": badge.get("GIFT", 0),
            "claimed": claimed,
            "lf_ac_next": c.lf_ac,
        }
    except Exception as e:
        return key, {"ok": False, "file": fname, "err": str(e)}


def main():
    creds = load_creds()
    if not creds:
        print(f"[!] ไม่พบบัญชีใน {CREDS} (และไม่พบไฟล์ creds.part*.json)")
        print("    ยังไม่มี credential บันทึกอยู่ในระบบสำหรับรับของ")
        print("    -> แนะนำให้รัน: python capture_auto.py ก่อน เพื่อจับ credential เข้าสู่ระบบ")
        return

    # process เฉพาะบัญชีที่ระบุ แต่ "คงบัญชีอื่นไว้ใน creds" (กันเขียนทับหาย)
    targets = [(k, creds[k]) for k in creds]
    if len(sys.argv) > 1:
        if sys.argv[1] not in creds:
            print(f"[X] ไม่พบ id '{sys.argv[1]}' (มี: {', '.join(creds) or '-'})")
            return
        targets = [(sys.argv[1], creds[sys.argv[1]])]

    print(f"[*] พบทั้งหมด {len(targets)} บัญชี ใน creds.json กำลังเริ่มล็อกอินและรับของอัตโนมัติผ่าน API...\n", flush=True)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=min(16, max(1, len(targets)))) as ex:
        for key, res in ex.map(lambda kv: _one(*kv), targets):
            results[key] = res
            # เก็บ LF_AC และค่า ruby/ticket ที่หมุนใหม่กลับ (บัญชี API เป็นเจ้าของ ต้องตามค่าล่าสุด)
            if res.get("ok"):
                entry = creds.setdefault(key, {})
                if res.get("lf_ac_next"):
                    entry["LF_AC"] = res.pop("lf_ac_next")
                if "ruby" in res:
                    entry["ruby"] = res["ruby"]
                if "ticket" in res:
                    entry["ticket"] = res["ticket"]
                if "coin" in res:
                    entry["coin"] = res["coin"]
            else:
                res.pop("lf_ac_next", None)
            ok = "OK " if res.get("ok") else "ERR"
            fname = res.get("file", "-")
            if res.get("ok"):
                ruby = res.get("ruby", 0)
                ticket = res.get("ticket", 0)
                coin = res.get("coin", 0)
                claimed = res.get("claimed", 0)
                print(f"[{ok}] {key:<10} | file={fname} | ruby={ruby} | ticket={ticket} | coin={coin} | claimed={claimed}", flush=True)
            else:
                print(f"[{ok}] {key:<10} | file={fname}: {res}", flush=True)

    _api_save_creds(creds, CREDS)
    good = sum(1 for r in results.values() if r.get("ok"))
    tot_claim = sum(r.get("claimed", 0) for r in results.values())
    print("\n" + "=" * 55, flush=True)
    print(f"สรุปผลการรับของอัตโนมัติ:", flush=True)
    print(f"  - สำเร็จ: {good}/{len(results)} บัญชี", flush=True)
    print(f"  - รับของขวัญรวม: {tot_claim} ชิ้น", flush=True)
    print(f"  - อัปเดตข้อมูลล่าสุดลง creds.json เรียบร้อย", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
