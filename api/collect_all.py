#!/usr/bin/env python3
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
from lgr_api import LGRClient, parse_ruby, parse_coin, parse_tickets

try:
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
except Exception:
    pass

CREDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def load_creds():
    try:
        with open(CREDS, "r", encoding="utf-8") as f:
            c = f.read().strip()
            return json.loads(c) if c else {}
    except Exception:
        return {}


def _one(key, cred):
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    fname = cred.get("file", "-")
    if not (udid and lf):
        return key, {"ok": False, "file": fname, "err": "no udid/LF_AC"}
    try:
        c = LGRClient(udid, lf)
        st, home = c.home()
        if st == 401:
            # LF_AC หมดอายุ -> ลอง /login ด้วย guestCookie
            gc = cred.get("guestCookie")
            if gc:
                c.login(gc)
                st, home = c.home()
        if st != 200:
            return key, {"ok": False, "file": fname, "step": "home", "status": st}
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
    # process เฉพาะบัญชีที่ระบุ แต่ "คงบัญชีอื่นไว้ใน creds" (กันเขียนทับหาย)
    targets = [(k, creds[k]) for k in creds]
    if len(sys.argv) > 1:
        if sys.argv[1] not in creds:
            print(f"[X] ไม่พบ id '{sys.argv[1]}' (มี: {', '.join(creds) or '-'})")
            return
        targets = [(sys.argv[1], creds[sys.argv[1]])]
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
                print(f"[{ok}] {key} | file={fname} | ruby={ruby} | ticket={ticket} | coin={coin} | claimed={claimed}")
            else:
                print(f"[{ok}] {key} | file={fname}: {res}")
    if os.path.exists(CREDS):
        import shutil
        shutil.copy2(CREDS, CREDS + ".bak")   # สำรองก่อนเขียนทับ (กันหายเหมือนที่เคยเจอ)
    json.dump(creds, open(CREDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    good = sum(1 for r in results.values() if r.get("ok"))
    tot_claim = sum(r.get("claimed", 0) for r in results.values())
    print(f"\nสรุป: {good}/{len(results)} บัญชีสำเร็จ, รับของรวม {tot_claim} ชิ้น")


if __name__ == "__main__":
    main()
