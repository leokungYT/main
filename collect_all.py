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
from lgr_api import LGRClient

try:
    sys.stdout.reconfigure(encoding="utf-8")   # กัน UnicodeEncodeError บน console Windows
except Exception:
    pass

CREDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creds.json")


def _one(key, cred):
    udid, lf = cred.get("udid"), cred.get("LF_AC")
    if not (udid and lf):
        return key, {"ok": False, "err": "no udid/LF_AC"}
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
            return key, {"ok": False, "step": "home", "status": st}
        badge = home.get("result", {}).get("badge", {})
        st_b, un = c.unclaimed_gifts()
        n = len(un or [])
        claimed = 0
        if n > 0:
            c.receive_all_gifts()
            st2, un2 = c.unclaimed_gifts()
            claimed = n - len(un2 or [])
        return key, {"ok": True, "gift_badge": badge.get("GIFT", 0),
                     "claimed": claimed, "lf_ac_next": c.lf_ac}
    except Exception as e:
        return key, {"ok": False, "err": str(e)}


def main():
    creds = json.load(open(CREDS, encoding="utf-8"))
    if len(sys.argv) > 1:
        creds = {k: v for k, v in creds.items() if k == sys.argv[1]}
    results = {}
    with cf.ThreadPoolExecutor(max_workers=min(16, max(1, len(creds)))) as ex:
        for key, res in ex.map(lambda kv: _one(*kv), creds.items()):
            results[key] = res
            # เก็บ LF_AC ที่หมุนใหม่กลับ (บัญชี API เป็นเจ้าของ ต้องตามค่าล่าสุด)
            if res.get("ok") and res.get("lf_ac_next"):
                creds.setdefault(key, {})["LF_AC"] = res.pop("lf_ac_next")
            else:
                res.pop("lf_ac_next", None)
            ok = "OK " if res.get("ok") else "ERR"
            print(f"[{ok}] {key}: {res}")
    json.dump(creds, open(CREDS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    good = sum(1 for r in results.values() if r.get("ok"))
    tot_claim = sum(r.get("claimed", 0) for r in results.values())
    print(f"\nสรุป: {good}/{len(results)} บัญชีสำเร็จ, รับของรวม {tot_claim} ชิ้น")


if __name__ == "__main__":
    main()
